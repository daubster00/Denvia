/**
 * 세션 종료 시 QA 대화 격리 — 2026-11-03 재수정 P0-2.
 *
 * QA 대화는 `denvia-qa-store`(sessionStorage 키)에 남는다. 세션이 끝나는 길이 여러
 * 갈래인데(로그아웃·API 401·SSE 401·중복 로그인·부팅 실패) 예전에는 각 경로가 제각기
 * 정리했고, 어떤 길은 로그인 사용자만 비우고 대화를 남겼다. 그러면 같은 탭의 다음
 * 사용자가 **이전 사용자의 대화**를 그대로 질문 맥락으로 보낸다.
 *
 * 이 파일이 고정하는 것:
 *   1. 공통 초기화 함수가 세션과 대화를 **함께** 비운다.
 *   2. 배포 전 저장 형식(주인 없는 대화)은 마이그레이션에서 안전하게 버려진다.
 *   3. 같은 사용자의 새로고침에서는 대화가 **유지된다**.
 */
import { beforeEach, describe, expect, it } from "vitest";

import {
  isAuthFailure,
  resetClientSession,
} from "@/features/auth/lib/session-reset";
import {
  QA_STORE_VERSION,
  useQAStore,
  type QAMessage,
} from "@/stores/qa-store";
import { useSessionStore } from "@/stores/session-store";
import { ApiError } from "@/types/api";

const TURN: QAMessage[] = [
  {
    id: "u1",
    role: "user",
    content: "스케일링 산정 기준",
    status: "complete",
    timestamp: "2026-01-01T00:00:00.000Z",
  },
  {
    id: "a1",
    role: "assistant",
    content: "3분의1악당 1회입니다.",
    status: "complete",
    qaLogId: 101,
    timestamp: "2026-01-01T00:00:00.000Z",
  },
];

beforeEach(() => {
  useQAStore.setState({ messages: [], pendingHomeQuestion: null, ownerUserId: null });
  useSessionStore.setState({ user: null } as never);
});

describe("공통 초기화 (resetClientSession)", () => {
  it.each([
    "logout",
    "api_401",
    "sse_401",
    "session_expired",
    "superseded",
    "bootstrap_failed",
  ] as const)("%s — 세션과 QA 대화를 모두 비운다", (reason) => {
    useQAStore.setState({
      messages: [...TURN],
      pendingHomeQuestion: "대기 질문",
      ownerUserId: 7,
    });
    useSessionStore.setState({ user: { user_id: 7 } } as never);

    resetClientSession(reason);

    const qa = useQAStore.getState();
    expect(qa.messages).toEqual([]);
    expect(qa.pendingHomeQuestion).toBeNull();
    expect(qa.ownerUserId).toBeNull();
    expect(useSessionStore.getState().user).toBeNull();
  });
});

describe("대화 주인 교체 (setOwner)", () => {
  it("같은 사용자의 새로고침에서는 대화를 유지한다", () => {
    useQAStore.setState({ messages: [...TURN], ownerUserId: 7 });

    useQAStore.getState().setOwner(7);

    expect(useQAStore.getState().messages.map((m) => m.id)).toEqual(["u1", "a1"]);
    expect(useQAStore.getState().ownerUserId).toBe(7);
  });

  it("다른 사용자가 들어오면 즉시 비운다", () => {
    useQAStore.setState({
      messages: [...TURN],
      pendingHomeQuestion: "이전 사용자의 대기 질문",
      ownerUserId: 7,
    });

    useQAStore.getState().setOwner(8);

    const qa = useQAStore.getState();
    expect(qa.messages).toEqual([]);
    expect(qa.pendingHomeQuestion).toBeNull();
    expect(qa.ownerUserId).toBe(8);
  });

  it("로그아웃 → 다른 계정 로그인 흐름에서 이전 대화가 남지 않는다", () => {
    // A 사용자가 대화한다.
    useQAStore.setState({ messages: [...TURN], ownerUserId: 7 });
    // 로그아웃.
    resetClientSession("logout");
    // 같은 탭에서 B 사용자가 로그인한다.
    useQAStore.getState().setOwner(8);

    expect(useQAStore.getState().messages).toEqual([]);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 배포 전 저장 형식 정리 — persist migrate
//
// `ownerUserId` 는 이번 작업에서 처음 들어온 필드다. 배포 직전에 열려 있던 탭에는
// 그 필드가 없는 대화가 남는다. `setOwner` 는 "주인이 없으면 현재 사용자를 주인으로
// 기록" 하므로, 그대로 두면 **남의 대화를 물려받는다**.
// ─────────────────────────────────────────────────────────────────────────────

/** persist 설정의 migrate 를 꺼내 직접 호출한다(저장 형식 단위 검증). */
function runMigrate(persisted: unknown) {
  const persistApi = (
    useQAStore as unknown as {
      persist: { getOptions: () => { migrate?: (s: unknown, v: number) => unknown } };
    }
  ).persist;
  const migrate = persistApi.getOptions().migrate;
  expect(migrate).toBeTypeOf("function");
  return migrate!(persisted, 0) as {
    messages?: QAMessage[];
    pendingHomeQuestion?: string | null;
    ownerUserId?: number | null;
  };
}

describe("구버전 sessionStorage 마이그레이션 (재수정 P0-2)", () => {
  it("저장 형식에 버전이 선언돼 있다", () => {
    const persistApi = (
      useQAStore as unknown as {
        persist: { getOptions: () => { version?: number } };
      }
    ).persist;
    expect(persistApi.getOptions().version).toBe(QA_STORE_VERSION);
  });

  it("주인 없는(ownerUserId 미존재) 대화는 버린다", () => {
    const migrated = runMigrate({
      messages: [...TURN],
      pendingHomeQuestion: "대기 질문",
    });

    expect(migrated.messages).toEqual([]);
    expect(migrated.pendingHomeQuestion).toBeNull();
    expect(migrated.ownerUserId).toBeNull();
  });

  it("ownerUserId 가 null 인 대화도 버린다", () => {
    const migrated = runMigrate({ messages: [...TURN], ownerUserId: null });
    expect(migrated.messages).toEqual([]);
  });

  it("주인 없는 대기 질문만 남아 있어도 버린다", () => {
    const migrated = runMigrate({
      messages: [],
      pendingHomeQuestion: "이전 사용자의 질문",
    });
    expect(migrated.pendingHomeQuestion).toBeNull();
  });

  it("주인이 기록된 대화는 그대로 유지한다 (같은 사용자 새로고침)", () => {
    const migrated = runMigrate({
      messages: [...TURN],
      pendingHomeQuestion: null,
      ownerUserId: 7,
    });
    expect(migrated.messages?.map((m) => m.id)).toEqual(["u1", "a1"]);
    expect(migrated.ownerUserId).toBe(7);
  });

  it("구버전 저장분 → 다른 계정 로그인 시 이전 대화가 전송되지 않는다", () => {
    // 배포 직전 탭에 남은 저장분(주인 없음)을 복원한 상태를 만든다.
    const migrated = runMigrate({ messages: [...TURN] });
    useQAStore.setState({
      messages: migrated.messages ?? [],
      pendingHomeQuestion: migrated.pendingHomeQuestion ?? null,
      ownerUserId: migrated.ownerUserId ?? null,
    });

    // 다른 계정이 로그인한다.
    useQAStore.getState().setOwner(8);

    expect(useQAStore.getState().messages).toEqual([]);
  });

  it("빈 저장분은 그대로 통과한다", () => {
    const migrated = runMigrate({ messages: [], ownerUserId: null });
    expect(migrated.messages).toEqual([]);
  });
});

describe("마이그레이션 — 쓸 수 없는 주인 값 (방어선)", () => {
  it.each([
    ["문자열", "7"],
    ["NaN", Number.NaN],
    ["Infinity", Number.POSITIVE_INFINITY],
    ["객체", { id: 7 }],
    ["true", true],
  ])("ownerUserId 가 %s 이면 대화를 버린다", (_label, owner) => {
    // setOwner 는 `===` 로 비교하므로 숫자가 아닌 주인은 영원히 일치하지 않는다.
    // 그대로 두면 대화가 탭에 영구히 남아 다음 사용자에게 넘어간다.
    const migrated = runMigrate({ messages: [...TURN], ownerUserId: owner });
    expect(migrated.messages).toEqual([]);
    expect(migrated.ownerUserId).toBeNull();
  });

  it("0 은 유효한 숫자이므로 그대로 둔다", () => {
    const migrated = runMigrate({ messages: [...TURN], ownerUserId: 0 });
    expect(migrated.messages?.length).toBe(2);
  });
});

describe("탈퇴 경로도 공통 초기화를 쓴다 (3차 검수 P2)", () => {
  it("탈퇴 후 다른 계정이 들어와도 대기 질문이 넘어가지 않는다", () => {
    useQAStore.setState({
      messages: [...TURN],
      pendingHomeQuestion: "탈퇴한 사용자의 대기 질문",
      ownerUserId: 7,
    });

    // 탈퇴가 호출하는 것과 동일한 공통 초기화.
    resetClientSession("logout");

    expect(useQAStore.getState().pendingHomeQuestion).toBeNull();
    expect(useQAStore.getState().messages).toEqual([]);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 일시 장애에서는 대화를 지우지 않는다 — 3차 검수 P1-1
//
// `/api/v1/me` 가 실패하는 이유는 인증 만료만이 아니다. 500·502·네트워크 단절도
// 같은 "실패" 로 들어온다. 그 전부를 세션 종료로 취급하면 **배포 중 20초간의 502**
// 만으로 진행 중인 대화가 통째로 사라진다(sessionStorage 를 지우므로 복구 불가).
// ─────────────────────────────────────────────────────────────────────────────

describe("isAuthFailure — 인증 실패만 세션 종료로 본다 (3차 검수 P1-1)", () => {
  it.each([
    "AUTH_SESSION_EXPIRED",
    "AUTH_SESSION_SUPERSEDED",
    "AUTH_NOT_AUTHENTICATED",
    "AUTH_INVALID_TOKEN",
    "ACCOUNT_BLOCKED",
  ])("%s 는 인증 실패다", (code) => {
    expect(
      isAuthFailure(new ApiError({ code, message: "x", trace_id: "t" })),
    ).toBe(true);
  });

  it.each([
    "INTERNAL_ERROR",
    "UNKNOWN_ERROR",
    "RATE_LIMITED",
    "KILLSWITCH_ACTIVE",
    "",
  ])("%s 는 인증 실패가 아니다 (대화를 지우면 안 된다)", (code) => {
    expect(
      isAuthFailure(new ApiError({ code, message: "x", trace_id: "t" })),
    ).toBe(false);
  });

  it("ApiError 가 아닌 오류(네트워크 단절 등)도 인증 실패가 아니다", () => {
    expect(isAuthFailure(new TypeError("Failed to fetch"))).toBe(false);
    expect(isAuthFailure(undefined)).toBe(false);
    expect(isAuthFailure(null)).toBe(false);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 복원 소독 — 3차 검수 P2
//
// `migrate` 는 저장 버전이 다를 때만 돈다. 같은 버전으로 저장됐지만 형식이 깨진 값
// (예: messages 가 객체)은 소독을 거치지 않고 복원돼 화면을 백화시켰다.
// ─────────────────────────────────────────────────────────────────────────────

function runMerge(persisted: unknown) {
  const persistApi = (
    useQAStore as unknown as {
      persist: {
        getOptions: () => {
          merge?: (p: unknown, c: unknown) => unknown;
        };
      };
    }
  ).persist;
  const merge = persistApi.getOptions().merge;
  expect(merge).toBeTypeOf("function");
  return merge!(persisted, useQAStore.getState()) as {
    messages?: QAMessage[];
    pendingHomeQuestion?: string | null;
    ownerUserId?: number | null;
  };
}

describe("복원 소독 (3차 검수 P2)", () => {
  it("messages 가 배열이 아니면 빈 배열로 만든다", () => {
    const merged = runMerge({ messages: { a: 1 }, ownerUserId: 7 });
    expect(Array.isArray(merged.messages)).toBe(true);
    expect(merged.messages).toEqual([]);
  });

  it("모양이 깨진 메시지 원소는 버린다", () => {
    const merged = runMerge({
      messages: [TURN[0], null, 42, { id: "x" }, TURN[1]],
      ownerUserId: 7,
    });
    expect(merged.messages?.map((m) => m.id)).toEqual(["u1", "a1"]);
  });

  it("pendingHomeQuestion 이 문자열이 아니면 null", () => {
    const merged = runMerge({
      messages: [],
      pendingHomeQuestion: { q: 1 },
      ownerUserId: 7,
    });
    expect(merged.pendingHomeQuestion).toBeNull();
  });

  it("persisted 가 null·배열이어도 터지지 않는다", () => {
    expect(runMerge(null).messages).toEqual([]);
    expect(runMerge([1, 2, 3]).messages).toEqual([]);
  });

  it("정상 저장분은 그대로 유지한다", () => {
    const merged = runMerge({
      messages: [...TURN],
      pendingHomeQuestion: null,
      ownerUserId: 7,
    });
    expect(merged.messages?.map((m) => m.id)).toEqual(["u1", "a1"]);
    expect(merged.ownerUserId).toBe(7);
  });
});
