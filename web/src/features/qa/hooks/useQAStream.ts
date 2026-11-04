"use client";

import { useRef } from "react";
import { useRouter } from "next/navigation";
import { fetchEventSource } from "@microsoft/fetch-event-source";
import { useQueryClient } from "@tanstack/react-query";
import { useQAStore, type QAMessage } from "@/stores/qa-store";
import { useAlertStore, type AlertAction } from "@/stores/alert-store";
import { resetClientSession } from "@/features/auth/lib/session-reset";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// 타자기 효과: 글자가 차르륵 흘러나오는 속도(ms/char).
// 너무 빠르면 한꺼번에 보이고, 너무 느리면 답답해진다.
const TYPEWRITER_CHAR_INTERVAL_MS = 28;
// 버퍼가 밀리면 한 틱에 여러 글자를 한꺼번에 흘려보내 따라잡는다.
function typewriterDrainCount(remaining: number): number {
  if (remaining > 200) return 8;
  if (remaining > 100) return 4;
  if (remaining > 40) return 2;
  return 1;
}

/**
 * 서버 요청 1건이 가리킬 수 있는 이전 대화 턴 수 상한.
 * 백엔드 스키마(`QAStreamRequest.history_turn_ids`)·`MAX_HISTORY_TURN_IDS` 와 **같은 값**.
 * 검수 P0-6 — 화면 대화가 31턴을 넘으면 요청이 통째로 422 로 거부됐다. 전송 직전에 자른다.
 */
export const MAX_HISTORY_TURN_IDS = 30;

/**
 * 지금까지의 대화를 **서버가 발급한 qa_log_id 목록**으로 바꾼다 (게시판 #149 · 검수 P0-2).
 *
 * 과거에는 질문·답변 문자열을 그대로 보냈다. 그러면 브라우저에서 과거 답변을 조작해
 * 프롬프트에 끼워 넣을 수 있고(프롬프트 주입), 계정이 바뀐 탭의 대화도 섞였다.
 * 지금은 id 만 보내고 본문은 서버가 자기 로그에서 읽는다.
 *
 * 보내는 턴의 조건:
 *   - 답변이 정상 완료(`complete`)이고 `qaLogId`(서버 발급 식별자)가 있다
 *     → 중단·오류 답변은 id 가 없거나 status 가 달라 자연히 빠진다(검수 P1-3)
 *   - 질문 본문이 비어 있지 않다
 *   - 마지막 `MAX_HISTORY_TURN_IDS` 개만 (오래된 것 → 최신 순)
 */
export function toHistoryTurnIds(messages: QAMessage[]): number[] {
  const ids: number[] = [];
  for (let i = 0; i < messages.length - 1; i += 1) {
    const q = messages[i];
    const a = messages[i + 1];
    if (q.role !== "user" || a.role !== "assistant") continue;
    if (a.status !== "complete") continue;
    if (typeof a.qaLogId !== "number" || !Number.isFinite(a.qaLogId)) continue;
    if (!q.content.trim()) continue;
    ids.push(a.qaLogId);
  }
  return ids.slice(-MAX_HISTORY_TURN_IDS);
}

export function useQAStream() {
  const router = useRouter();
  const addMessage = useQAStore((s) => s.addMessage);
  const pruneGhostTurns = useQAStore((s) => s.pruneGhostTurns);
  const dropTurn = useQAStore((s) => s.dropTurn);
  const addToken = useQAStore((s) => s.addToken);
  const markRuleMatched = useQAStore((s) => s.markRuleMatched);
  const finalize = useQAStore((s) => s.finalize);
  const setError = useQAStore((s) => s.setError);
  const abortRef = useRef<AbortController | null>(null);
  const queryClient = useQueryClient();

  /**
   * 질문 전송.
   *
   * `retry` — 사용자가 "다시 시도" 를 눌러 보내는 요청인지. 이전 대화가 딸린 질문은
   * 이 값이 true 이고 서버가 만든 맥락 지문까지 같을 때만, 전송 못 한 저장 답변이
   * 재생된다(검수 P0-1).
   *
   * `historyTurnIds` — 보낼 이전 대화를 **호출부가 직접 지정**한다. 과거 오류 답변의
   * 재시도에서 쓴다(재수정 P1-2): 지금 화면 전체를 다시 계산하면 재시도 대상보다
   * 뒤에 일어난 대화가 맥락으로 섞인다. 생략하면 현재 대화에서 계산한다.
   */
  async function submit(
    questionText: string,
    options?: { retry?: boolean; historyTurnIds?: number[] },
  ) {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    const userId = crypto.randomUUID();
    const assistantId = crypto.randomUUID();
    const now = new Date().toISOString();

    // 게시판 #149: 대화 이어가기. 새 질문을 **지우지 않고 아래에 쌓는다**.
    // (기존에는 클라이언트 기획서 §3 에 따라 매 질문마다 이전 대화를 전부 지웠다.)
    //
    // 먼저 유령 턴을 청소한다 — 위에서 abort 한 직전 스트림이나, 홈→/chat 이동 중
    // 중복 제출로 생긴 빈 답변이 pending 으로 남으면 입력창이 영구히 잠긴다.
    pruneGhostTurns();
    // 서버로 보낼 이전 대화는 이번 질문을 추가하기 **전** 상태에서 뽑는다.
    // 재시도는 최초 요청 당시의 스냅샷을 그대로 쓴다(재수정 P1-2).
    const historyTurnIds = (
      options?.historyTurnIds ?? toHistoryTurnIds(useQAStore.getState().messages)
    ).slice(-MAX_HISTORY_TURN_IDS);

    addMessage({
      id: userId,
      role: "user",
      content: questionText,
      status: "complete",
      timestamp: now,
    });
    addMessage({
      id: assistantId,
      role: "assistant",
      content: "",
      status: "pending",
      // 재수정 P1-2 — 이 답변이 **어떤 맥락으로** 요청됐는지 박아 둔다.
      // 나중에 이 답변을 재시도할 때 그때의 전체 대화를 다시 계산하지 않기 위함.
      historyTurnIds,
      timestamp: now,
    });

    // 타자기 버퍼 — SSE 토큰이 들어오는 즉시 store에 찍지 않고 글자 단위 큐로 보낸다.
    // 백엔드는 토큰을 묶어 보낼 때가 있어서 그대로 찍으면 "한꺼번에 팍" 보인다.
    const charBuffer: string[] = [];
    let typewriterTimer: ReturnType<typeof setInterval> | null = null;
    let streamFinished = false;
    let pendingFinalizeId: number | null = null;
    let typewriterDone: () => void = () => {};
    const typewriterPromise = new Promise<void>((resolve) => {
      typewriterDone = resolve;
    });

    const startTypewriter = () => {
      if (typewriterTimer !== null) return;
      typewriterTimer = setInterval(() => {
        const remaining = charBuffer.length;
        if (remaining > 0) {
          const n = typewriterDrainCount(remaining);
          const chunk = charBuffer.splice(0, n).join("");
          addToken(assistantId, chunk);
          return;
        }
        if (streamFinished) {
          if (typewriterTimer !== null) {
            clearInterval(typewriterTimer);
            typewriterTimer = null;
          }
          if (pendingFinalizeId !== null) {
            finalize(assistantId, pendingFinalizeId);
            queryClient.invalidateQueries({ queryKey: ["me", "quota"] });
            pendingFinalizeId = null;
          }
          typewriterDone();
        }
      }, TYPEWRITER_CHAR_INTERVAL_MS);
    };

    // 중단 시점에 타자기 큐에 아직 안 찍힌 글자가 남아 있으면 화면에 마저 붙인다.
    // 부분 답변을 한 글자라도 더 보존하기 위함 (게시판 #141).
    const flushBuffer = () => {
      if (charBuffer.length > 0) {
        addToken(assistantId, charBuffer.splice(0).join(""));
      }
    };

    const cleanupTypewriter = () => {
      if (typewriterTimer !== null) {
        clearInterval(typewriterTimer);
        typewriterTimer = null;
      }
      charBuffer.length = 0;
      typewriterDone();
    };

    controller.signal.addEventListener("abort", cleanupTypewriter);

    try {
      await fetchEventSource(`${API_BASE}/api/v1/qa/stream`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question_text: questionText,
          history_turn_ids: historyTurnIds,
          retry: options?.retry === true,
        }),
        signal: controller.signal,
        openWhenHidden: true,
        async onopen(response) {
          // 세션이 끝난 뒤 보낸 질문 — 재수정 P0-2.
          // SSE 는 `apiFetch` 를 타지 않으므로 공용 401 인터셉터가 걸리지 않는다.
          // 여기서 처리하지 않으면 로그아웃·중복 로그인 이후에도 이전 사용자의 대화가
          // 탭에 남아, 다음 사용자의 첫 질문 맥락으로 전송된다.
          if (response.status === 401) {
            const body = await response.json().catch(() => ({}));
            const code = (body?.code as string | undefined) ?? "";
            const superseded = code === "AUTH_SESSION_SUPERSEDED";
            resetClientSession(superseded ? "superseded" : "sse_401");
            useAlertStore.getState().show({
              level: "warning",
              title: superseded
                ? "다른 장소에서 로그인되어 로그아웃되었습니다."
                : "로그인이 만료되어 답변을 받지 못했어요.",
              description: "다시 로그인한 뒤 질문해 주세요.",
              dedupeKey: superseded ? "session-superseded" : "sse-session-expired",
            });
            controller.abort();
            return;
          }

          // Story 2.3: SSE 시작 전 429 분기 (일반 JSON 응답 — SSE 아님)
          //
          // 재수정 P1-4 — 예전에는 아는 코드 2개(QUOTA_EXCEEDED,
          // QUOTA_EXCEEDED_INTERNAL_SAFETY_LIMIT)에서만 이번 턴을 걷어냈다.
          // 예산 소진 차단(BUDGET_HARD_CAP_REACHED)이나 알 수 없는 429 는 그냥
          // `!response.ok` 로 떨어져, **빈 답변 말풍선이 오류 상태로 화면에 남았다**.
          // 스트림이 시작되기 전의 429 는 어떤 코드든 "이번 질문이 거절된 것" 이므로
          // 이번 턴만 제거하고 과거 정상 대화는 보존한다.
          if (response.status === 429) {
            const body = await response.json().catch(() => ({}));
            const code = body?.code as string | undefined;
            const details = (body?.details ?? body) as Record<string, unknown>;
            const isQuota =
              code === "QUOTA_EXCEEDED" ||
              code === "QUOTA_EXCEEDED_INTERNAL_SAFETY_LIMIT";
            const isInternal = code === "QUOTA_EXCEEDED_INTERNAL_SAFETY_LIMIT";

            if (isQuota) {
              const dailyLimit = (details.daily_limit as number | undefined) ?? 10;
              const showSubscribe =
                (details.show_subscribe_button as boolean | undefined) ?? true;

              const actions: AlertAction[] = isInternal
                ? [{ label: "확인", variant: "normal" }]
                : [
                    { label: "내일 다시", variant: "assistive" },
                    ...(showSubscribe
                      ? [
                          {
                            label: "Pro로 계속",
                            variant: "normal" as const,
                            onClick: () => router.push("/subscribe"),
                          },
                        ]
                      : []),
                  ];

              useAlertStore.getState().show({
                level: "warning",
                title: isInternal
                  ? "일시적 시스템 보호 제한에 도달했습니다."
                  : `오늘의 ${dailyLimit}회를 모두 사용했어요.`,
                description: isInternal
                  ? "고객문의로 연락주세요."
                  : "내일 다시 오시거나, Pro로 계속 진료에 활용해보세요.",
                actions,
                dedupeKey: code,
              });
            } else if (code === "BUDGET_HARD_CAP_REACHED") {
              // 월 예산 소진으로 무료 질의가 일시 중단된 상태. 사용자가 고칠 수 있는
              // 것이 아니므로 무엇이 막혔고 언제 풀리는지만 담백하게 알린다.
              useAlertStore.getState().show({
                level: "warning",
                title: "이번 달 무료 질문이 일시 중단되었습니다.",
                description:
                  "다음 달에 다시 열립니다. 바로 쓰셔야 하면 Pro 구독을 확인해 주세요.",
                actions: [
                  { label: "확인", variant: "assistive" },
                  {
                    label: "Pro로 계속",
                    variant: "normal" as const,
                    onClick: () => router.push("/subscribe"),
                  },
                ],
                dedupeKey: code,
              });
            } else {
              // 알 수 없는 429 — 서버 문구를 그대로 보여주고 재시도를 안내한다.
              useAlertStore.getState().show({
                level: "warning",
                title:
                  (body?.message as string | undefined) ??
                  "요청이 많아 잠시 처리할 수 없어요.",
                description: "잠시 후 다시 시도해 주세요.",
                dedupeKey: code ?? "qa-429",
              });
            }

            // 검수 P1-5 + 재수정 P1-4 — 누적 대화 모드에서는 **이번 거절된 턴만**
            // 걷어낸다. 예전 1문1답 정책의 clearMessages() 는 과거 정상 대화까지 지웠다.
            dropTurn(assistantId);
            controller.abort();
            return;
          }
          // 3차 검수 P1-5 — **스트림 시작 전 나머지 비정상 상태도 같은 방식으로** 처리한다.
          //
          // 예전에는 401·429 만 다루고 그 외는 throw 로 떨어뜨렸다. 그러면 catch 가
          // "인터넷 연결이 끊겨 답변이 중단됐어요" 를 붙이는데, 실제 원인은 전혀
          // 다르다. 특히 아래 둘은 운영 상시 기능이라 체감 영향이 크다.
          //   - 503 KILLSWITCH_ACTIVE: 관리자가 서비스를 일시 중단한 상태.
          //     서버가 "재개 시 알림톡으로 안내드립니다" 라는 정확한 문구를 주는데
          //     그게 버려지고 **사용자 탓(인터넷)으로 읽히는 문구**가 나갔다.
          //   - 422 QUESTION_TOO_LONG: 관리자가 글자수 상한을 프런트 기본값보다
          //     낮추면 즉시 발생한다.
          // 게다가 dropTurn 을 타지 않아 **빈 답변 말풍선이 오류 상태로 영구히 남았다**
          // (대화가 누적되는 지금은 이후 대화에 계속 보인다).
          if (!response.ok) {
            const body = await response.json().catch(() => ({}));
            const code = (body?.code as string | undefined) ?? "";
            const serverMessage = body?.message as string | undefined;
            const isBlocked = response.status === 503;
            useAlertStore.getState().show({
              level: "warning",
              title: isBlocked
                ? "지금은 질문을 받을 수 없어요."
                : "질문을 보내지 못했어요.",
              description:
                serverMessage ??
                (isBlocked
                  ? "서비스가 일시 중단되었습니다. 재개되면 안내드립니다."
                  : "잠시 후 다시 시도해 주세요."),
              dedupeKey: code || `qa-http-${response.status}`,
            });
            // 보내지 못한 질문이므로 이번 턴만 걷어낸다 — 과거 대화는 보존.
            dropTurn(assistantId);
            controller.abort();
            return;
          }
        },
        onmessage(ev) {
          // #142 후속 — sse-starlette 기본 15초 keep-alive ping(`: ping` 주석)이
          // fetch-event-source 파서에서 data 없는 빈 메시지로 dispatch된다. 이를 걸러내지
          // 않고 JSON.parse('') 하면 SyntaxError가 나 스트림이 통째로 abort → 15초를 넘기는
          // 장문 답변이 "연결 끊김"으로 중단됐다. 빈 data(핑·주석)는 조용히 건너뛴다.
          if (!ev.data) return;
          const data = JSON.parse(ev.data);
          if (ev.event === "token") {
            // 글자 단위로 큐에 쌓고 타자기를 가동한다 (스프레드 = Unicode safe split).
            // 3차 검수 P2 — delta 가 없거나 문자열이 아니면 전개에서 TypeError 가 나
            // 스트림이 통째로 abort 되고 "인터넷 연결이 끊겨…" 로 보였다. 건너뛴다.
            const delta = data?.delta;
            if (typeof delta !== "string" || delta.length === 0) return;
            for (const ch of [...delta]) charBuffer.push(ch);
            startTypewriter();
          }
          else if (ev.event === "rule_matched") markRuleMatched(assistantId, data.procedure_count);
          else if (ev.event === "done") {
            // 타자기 버퍼가 비워진 다음 finalize 한다.
            streamFinished = true;
            pendingFinalizeId = data.qa_log_id;
            // 이상 질문 패턴 탐지로 throttle 이 새로 적용되었고, 무료 사용자라면
            // 안내 팝업을 띄운다. 유료 사용자는 throttle 적용되어도 팝업 미노출
            // (백엔드 done 이벤트에서 show_popup 을 false 로 내려준다).
            if (data?.show_popup === true) {
              const anomalyType = data?.anomaly_type as string | null | undefined;
              const { title, description } =
                anomalyType === "repeated_question"
                  ? {
                      title: "같은 질문이 반복되어 이상탐지 되었습니다.",
                      description: "답변의 속도를 제한합니다.",
                    }
                  : {
                      title: "질문의 속도가 비정상적으로 빨라 이상탐지 되었습니다.",
                      description: "답변의 속도를 제한합니다.",
                    };
              useAlertStore.getState().show({
                level: "warning",
                title,
                description,
                dedupeKey: "anomaly_throttle_applied",
              });
            }
            startTypewriter();
          }
          else if (ev.event === "error") {
            flushBuffer();
            cleanupTypewriter();
            setError(assistantId, data.message);
          }
        },
        onerror(err) {
          throw err;
        },
      });
      // SSE는 끝났지만 타자기 버퍼가 남아있을 수 있다 — 다 흘러나올 때까지 대기.
      if (typewriterTimer !== null) {
        await typewriterPromise;
      }
    } catch (err) {
      flushBuffer();
      cleanupTypewriter();
      if ((err as Error).name !== "AbortError") {
        // 대개 유저↔서버 연결이 중간에 끊긴 경우(프록시/네트워크). 지금까지 받은
        // 부분 답변은 화면에 남겨두고(setError 가 content 를 지우지 않음) 안내만 붙인다.
        setError(assistantId, "인터넷 연결이 끊겨 답변이 중단됐어요. 다시 시도해 주세요.");
      }
    }
  }

  function abort() {
    abortRef.current?.abort();
    abortRef.current = null;
  }

  return { submit, abort };
}
