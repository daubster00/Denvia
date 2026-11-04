"use client";

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

export interface QAMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  qaLogId?: number;
  status: "pending" | "complete" | "error";
  ruleMatched?: boolean;
  procedureCount?: number;
  // 스트림이 중간에 끊겼을 때(연결 단절 등) 노출할 안내 문구.
  // content(지금까지 받은 부분 답변)는 지우지 않고 보존하고, 이 필드만 별도로 채운다.
  errorMessage?: string;
  /**
   * 이 답변을 **최초로 요청할 때 서버에 보낸** 이전 대화 턴 id 목록 (재수정 P1-2).
   *
   * 과거 오류 답변의 "다시 시도" 는 지금 화면의 전체 대화를 다시 계산해서는 안 된다.
   * A 가 실패한 뒤 B 가 정상 완료됐다면, A 를 재시도할 때 B 의 로그 id 까지 맥락으로
   * 보내게 되고 — 시간상 **A 보다 뒤에 일어난 대화**가 A 의 맥락이 된다. 서버가 만드는
   * 맥락 지문도 달라져 저장 답변 재생(#141)이 어긋난다.
   *
   * 그래서 최초 요청 당시의 맥락을 그대로 스냅샷해 둔다. 재시도는 이 값을 쓴다.
   * 구버전 메시지(이 필드가 없는 sessionStorage 잔존분)는 호출부가
   * `historyTurnIdsBefore()` 로 **그 질문 이전의 완료 턴만** 계산해 폴백한다.
   */
  historyTurnIds?: number[];
  timestamp: string;
}

/** 이 저장소 형식의 버전 — 올리면 `migrate` 가 돈다 (재수정 P0-2). */
export const QA_STORE_VERSION = 1;

/** 저장소 키 — 진단·테스트에서 참조한다. */
export const QA_STORE_NAME = "denvia-qa-store";

interface QAStore {
  messages: QAMessage[];
  // 홈(/)에서 보낸 질문을 /chat 으로 라우팅이 끝난 다음 stream 으로 흘려보내기 위한 대기 슬롯.
  // 컴포넌트 useRef 는 페이지 라우팅(/ → /chat) 시 unmount 로 소실되므로 store 에 보관한다.
  pendingHomeQuestion: string | null;
  /**
   * 이 대화의 주인 user_id (검수 P0-4).
   *
   * 대화는 sessionStorage 에 남으므로, 같은 탭에서 로그아웃 후 다른 계정으로 들어오면
   * 이전 사용자의 대화가 그대로 남아 다음 질문의 맥락으로 전송됐다. 주인이 바뀌면
   * 즉시 비운다. 같은 사용자의 새로고침·페이지 이동에서는 그대로 유지한다.
   */
  ownerUserId: number | null;
  setPendingHomeQuestion: (q: string | null) => void;
  addMessage: (msg: QAMessage) => void;
  updateMessage: (id: string, patch: Partial<QAMessage>) => void;
  clearMessages: () => void;
  /** 세션 소유자 확정 — 주인이 바뀌면 대화를 전부 비운다 (검수 P0-4). */
  setOwner: (userId: number | null) => void;
  /** 로그아웃·강제 종료 시 호출 — 대화·대기 질문·주인 정보를 모두 비운다 (검수 P0-4). */
  resetForSessionEnd: () => void;
  /** 끝나지 않은(pending) 답변을 정리한다 — 대화 누적 모드의 필수 청소(#149). */
  pruneGhostTurns: () => void;
  /** 질문 1턴(사용자 질문 + 그 답변)을 제거한다 — 한도 거절 등에서 사용 (검수 P1-5). */
  dropTurn: (assistantId: string) => void;
  // 클라이언트 기획서 §3: 새 질문 시 이전 대화는 사라지고 신규 1질의응답만 표시 (atomic 교체로 hero variant 깜빡임 방지)
  replaceMessages: (msgs: QAMessage[]) => void;
  addToken: (id: string, delta: string) => void;
  markRuleMatched: (id: string, procedureCount: number) => void;
  finalize: (id: string, qaLogId: number) => void;
  setError: (id: string, message: string) => void;
}

/** 복원된 메시지 1건이 화면·전송 로직이 기대하는 모양인가. */
function isUsableMessage(m: unknown): m is QAMessage {
  if (typeof m !== "object" || m === null) return false;
  const v = m as Partial<QAMessage>;
  return (
    typeof v.id === "string" &&
    (v.role === "user" || v.role === "assistant") &&
    typeof v.content === "string" &&
    (v.status === "pending" || v.status === "complete" || v.status === "error")
  );
}

/**
 * sessionStorage 에서 복원된 값을 안전한 상태로 정리한다 (재수정 P0-2 · 3차 검수 P2).
 *
 * 두 가지를 막는다.
 *
 * 1. **주인 없는 대화** — `ownerUserId`(이 대화의 주인 user_id)는 이번 작업에서 처음
 *    들어온 필드다. 배포 직전에 열려 있던 탭에는 그 필드가 없는 대화가 남는데,
 *    `setOwner` 는 "주인이 없으면 현재 사용자를 주인으로 기록" 하므로 그대로 두면
 *    **남의 대화를 물려받는다.** 주인을 모르면 대화와 대기 질문을 버린다.
 *    문자열 `"7"`·NaN·Infinity 처럼 `===` 비교에서 절대 일치할 수 없는 값도
 *    "주인 없음" 으로 본다 — 그대로 두면 대화가 탭에 영구히 남는다.
 * 2. **형식이 깨진 값** — `messages` 가 배열이 아니거나 원소 모양이 다르면 화면
 *    렌더링(`messages.map`)과 유령 턴 청소(`for...of`)가 TypeError 로 터진다.
 */
function sanitizePersisted(persisted: unknown): Partial<QAStore> {
  const state = (typeof persisted === "object" && persisted !== null
    ? persisted
    : {}) as Partial<QAStore>;

  const messages = Array.isArray(state.messages)
    ? state.messages.filter(isUsableMessage)
    : [];
  const pendingHomeQuestion =
    typeof state.pendingHomeQuestion === "string" ? state.pendingHomeQuestion : null;
  const ownerUserId = Number.isFinite(state.ownerUserId as number)
    ? (state.ownerUserId as number)
    : null;

  if (ownerUserId === null) {
    // 주인을 모르는 대화·대기 질문은 다음 사용자에게 넘어갈 수 있다 → 버린다.
    return { ...state, messages: [], pendingHomeQuestion: null, ownerUserId: null };
  }
  return { ...state, messages, pendingHomeQuestion, ownerUserId };
}

export const useQAStore = create<QAStore>()(
  persist(
    (set) => ({
      messages: [],
      pendingHomeQuestion: null,
      ownerUserId: null,
      setPendingHomeQuestion: (q) => set({ pendingHomeQuestion: q }),
      // 검수 P0-4 — 같은 탭에서 계정이 바뀌면 이전 사용자의 대화를 지운다.
      // 같은 사용자(또는 아직 주인이 없던 상태)면 대화를 건드리지 않는다.
      setOwner: (userId) =>
        set((s) => {
          if (userId === null) return s;
          if (s.ownerUserId === null) return { ...s, ownerUserId: userId };
          if (s.ownerUserId === userId) return s;
          return {
            ...s,
            ownerUserId: userId,
            messages: [],
            pendingHomeQuestion: null,
          };
        }),
      resetForSessionEnd: () =>
        set({ messages: [], pendingHomeQuestion: null, ownerUserId: null }),
      addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
      updateMessage: (id, patch) =>
        set((s) => ({
          messages: s.messages.map((m) => (m.id === id ? { ...m, ...patch } : m)),
        })),
      clearMessages: () => set({ messages: [] }),
      // 게시판 #149: 대화를 지우지 않고 쌓게 되면서, 중단된 답변이 pending 으로 남으면
      // "답변 중" 상태가 영원히 풀리지 않아 입력창이 잠긴다(이전에는 매 질문마다 전체를
      // 지워서 드러나지 않던 문제). 새 질문을 보내기 직전에 이걸로 청소한다.
      //   - 내용이 일부라도 있으면: **중단 상태(error)** 로 남긴다 — 화면에는 보존하되
      //     정상 완료로 승격하지 않는다(검수 P1-3). 완료되지 않은 답변을 complete 로
      //     바꾸면 다음 질문의 맥락으로 올라가, 반쪽 답변이 신뢰된 대화가 돼 버린다.
      //   - 내용이 비었으면: 유령 턴이므로 직전 질문과 함께 제거
      pruneGhostTurns: () =>
        set((s) => {
          const out: QAMessage[] = [];
          for (const m of s.messages) {
            if (m.role === "assistant" && m.status === "pending") {
              if ((m.content ?? "").trim()) {
                out.push({
                  ...m,
                  status: "error",
                  errorMessage:
                    m.errorMessage ?? "답변이 중간에 끊겼어요. 다시 시도해 주세요.",
                });
              } else if (out.length > 0 && out[out.length - 1].role === "user") {
                out.pop();
              }
              continue;
            }
            out.push(m);
          }
          return { messages: out };
        }),
      // 검수 P1-5 — 한도 거절(429) 등에서 "이번 턴만" 걷어낸다. 과거 정상 대화는 보존.
      dropTurn: (assistantId) =>
        set((s) => {
          const idx = s.messages.findIndex((m) => m.id === assistantId);
          if (idx === -1) return s;
          const from =
            idx > 0 && s.messages[idx - 1].role === "user" ? idx - 1 : idx;
          return {
            messages: [...s.messages.slice(0, from), ...s.messages.slice(idx + 1)],
          };
        }),
      replaceMessages: (msgs) => set({ messages: msgs }),
      addToken: (id, delta) =>
        set((s) => ({
          messages: s.messages.map((m) =>
            m.id === id ? { ...m, content: m.content + delta } : m
          ),
        })),
      markRuleMatched: (id, procedureCount) =>
        set((s) => ({
          messages: s.messages.map((m) =>
            m.id === id ? { ...m, ruleMatched: true, procedureCount } : m
          ),
        })),
      finalize: (id, qaLogId) =>
        set((s) => ({
          messages: s.messages.map((m) =>
            m.id === id ? { ...m, qaLogId, status: "complete" } : m
          ),
        })),
      // 스트림 중단 시 — 지금까지 받은 부분 답변(content)은 그대로 두고,
      // 안내 문구만 errorMessage 에 담는다. (과거엔 content 를 에러 문구로 통째
      // 교체해 "나오던 답변이 사라지는" 현상이 있었다 — 게시판 #141.)
      setError: (id, message) =>
        set((s) => ({
          messages: s.messages.map((m) =>
            m.id === id ? { ...m, status: "error", errorMessage: message } : m
          ),
        })),
    }),
    {
      name: QA_STORE_NAME,
      storage: createJSONStorage(() => sessionStorage),
      version: QA_STORE_VERSION,
      /**
       * 배포 전 형식으로 저장된 대화 정리 — 재수정 P0-2.
       *
       * `ownerUserId`(이 대화의 주인) 는 이번 작업에서 처음 들어온 필드다. 배포 **직전에**
       * 열려 있던 탭의 `sessionStorage` 에는 그 필드가 없는 대화가 남아 있다. 주인을 모르는
       * 대화는 다음에 로그인한 사용자의 것인지 확인할 방법이 없는데, `setOwner` 는
       * "주인이 없으면 현재 사용자를 주인으로 기록" 하도록 만들어져 있다 —
       * 즉 **남의 대화를 그대로 물려받는다.**
       *
       * 그래서 마이그레이션 단계에서 주인 없는 대화는 안전하게 버린다. 잃는 것은
       * 배포 순간에 열려 있던 탭의 화면 이력뿐이고(서버 기록은 그대로 남는다),
       * 막는 것은 계정 간 대화 유출이다.
       */
      migrate: (persisted: unknown, _version: number) => sanitizePersisted(persisted),
      /**
       * 복원된 값을 **버전과 무관하게** 소독한다 (3차 검수 P2).
       *
       * `migrate` 는 저장된 버전이 현재 버전과 **다를 때만** 돈다. 그래서 같은 버전으로
       * 저장됐지만 형식이 깨진 값(예: `messages` 가 객체)은 소독을 거치지 않고 그대로
       * 복원돼, `messages.map` / `for...of` 에서 TypeError 가 나 채팅 화면이 백화됐다.
       * `merge` 는 복원 때마다 돌기 때문에 여기서 한 번 더 막는다.
       */
      merge: (persisted, current) => ({
        ...current,
        ...sanitizePersisted(persisted),
      }),
    }
  )
);

/**
 * 재시도 대상 질문 **이전**의 완료 턴 id 만 계산한다 (재수정 P1-2 의 폴백).
 *
 * 스냅샷(`QAMessage.historyTurnIds`)이 없는 구버전 메시지에 쓴다. 지금 화면의 전체
 * 대화를 쓰면 재시도 대상보다 **뒤에 일어난 대화**가 맥락으로 들어간다.
 *
 * @param messages 현재 대화 전체
 * @param assistantMessageId 재시도할 답변 메시지 id
 */
export function historyTurnIdsBefore(
  messages: QAMessage[],
  assistantMessageId: string,
): number[] {
  const idx = messages.findIndex((m) => m.id === assistantMessageId);
  if (idx <= 0) return [];
  // 재시도 대상 답변 바로 앞이 그 질문이다. 그 질문보다 앞의 턴만 맥락이 된다.
  const questionIdx = messages[idx - 1].role === "user" ? idx - 1 : idx;
  const ids: number[] = [];
  for (let i = 0; i < questionIdx - 1; i += 1) {
    const q = messages[i];
    const a = messages[i + 1];
    if (q.role !== "user" || a.role !== "assistant") continue;
    if (a.status !== "complete") continue;
    if (typeof a.qaLogId !== "number" || !Number.isFinite(a.qaLogId)) continue;
    if (!q.content.trim()) continue;
    ids.push(a.qaLogId);
  }
  return ids;
}
