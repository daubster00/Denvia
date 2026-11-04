/**
 * useQAStream — 거절 응답 처리와 맥락 스냅샷. 2026-11-03 재수정 P0-2 · P1-2 · P1-4.
 *
 * 고정하는 것:
 *   - **모든 429** 에서 이번 거절된 턴만 사라지고 과거 정상 대화는 보존된다 (P1-4).
 *     예전에는 아는 코드 2개에서만 그렇게 했고, 예산 소진 차단이나 알 수 없는 429 는
 *     빈 답변 말풍선을 오류 상태로 화면에 남겼다.
 *   - **SSE 401** 에서 로그인 세션과 QA 대화를 함께 비운다 (P0-2). SSE 는 apiFetch 를
 *     타지 않으므로 공용 401 인터셉터가 걸리지 않는다.
 *   - 답변 메시지에 **최초 요청 당시의 맥락**이 스냅샷된다 (P1-2).
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { renderHook } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush, replace: vi.fn() }),
  usePathname: () => "/chat",
  useSearchParams: () => new URLSearchParams(),
}));

const fetchEventSourceMock = vi.fn();
vi.mock("@microsoft/fetch-event-source", () => ({
  fetchEventSource: (...args: unknown[]) => fetchEventSourceMock(...args),
}));

import {
  useQAStream,
  MAX_HISTORY_TURN_IDS,
} from "@/features/qa/hooks/useQAStream";
import { useQAStore, type QAMessage } from "@/stores/qa-store";
import { useAlertStore } from "@/stores/alert-store";
import { useSessionStore } from "@/stores/session-store";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const PAST_TURN: QAMessage[] = [
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

const LATER_TURN: QAMessage[] = [
  {
    id: "u2",
    role: "user",
    content: "뒤에 물어본 질문",
    status: "complete",
    timestamp: "2026-01-01T00:01:00.000Z",
  },
  {
    id: "a2",
    role: "assistant",
    content: "뒤 답변",
    status: "complete",
    qaLogId: 202,
    timestamp: "2026-01-01T00:01:00.000Z",
  },
];

function alertShown(): boolean {
  const alerts = useAlertStore.getState() as unknown as {
    queue?: unknown[];
    current?: unknown;
  };
  return Boolean(alerts.queue?.length || alerts.current);
}

function mockStatus(status: number, body: Record<string, unknown>) {
  fetchEventSourceMock.mockImplementation(async (_url: string, opts: never) => {
    const options = opts as unknown as { onopen: (r: Response) => Promise<void> };
    await options.onopen({
      status,
      ok: false,
      json: async () => body,
    } as unknown as Response);
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  useQAStore.setState({ messages: [], pendingHomeQuestion: null, ownerUserId: null });
  useAlertStore.setState({ queue: [] } as never);
  useSessionStore.setState({ user: null } as never);
});

// ─────────────────────────────────────────────────────────────────────────────
// 모든 429 에서 이번 턴만 제거 — 재수정 P1-4
// ─────────────────────────────────────────────────────────────────────────────

const CASES_429: Array<[string, string | undefined, Record<string, unknown>]> = [
  ["일일 한도", "QUOTA_EXCEEDED", { daily_limit: 10, show_subscribe_button: true }],
  ["내부 보호 한도", "QUOTA_EXCEEDED_INTERNAL_SAFETY_LIMIT", {}],
  ["예산 소진 차단", "BUDGET_HARD_CAP_REACHED", {}],
  ["코드 없는 429", undefined, {}],
];

describe("모든 429 에서 현재 거절 턴만 제거 (재수정 P1-4)", () => {
  it.each(CASES_429)(
    "%s — 과거 대화는 보존하고 이번 턴만 제거한다",
    async (_label, code, details) => {
      useQAStore.setState({ messages: [...PAST_TURN] });
      mockStatus(429, { code, message: "한도에 도달했습니다", details });

      const { result } = renderHook(() => useQAStream(), { wrapper });
      await result.current.submit("거절될 질문");

      const messages = useQAStore.getState().messages;
      expect(messages.map((m) => m.id)).toEqual(["u1", "a1"]);
      // 빈 답변 말풍선이 오류 상태로 남지 않는다.
      expect(
        messages.some((m) => m.role === "assistant" && m.content === ""),
      ).toBe(false);
    },
  );

  it.each(CASES_429)("%s — 안내를 표시한다", async (_label, code, details) => {
    mockStatus(429, { code, message: "한도에 도달했습니다", details });

    const { result } = renderHook(() => useQAStream(), { wrapper });
    await result.current.submit("거절될 질문");

    expect(alertShown()).toBe(true);
  });

  it("429 가 과거 대화를 통째로 지우지 않는다 (clearMessages 회귀 금지)", async () => {
    useQAStore.setState({ messages: [...PAST_TURN, ...LATER_TURN] });
    mockStatus(429, { code: "BUDGET_HARD_CAP_REACHED", details: {} });

    const { result } = renderHook(() => useQAStream(), { wrapper });
    await result.current.submit("거절될 질문");

    expect(useQAStore.getState().messages.map((m) => m.id)).toEqual([
      "u1",
      "a1",
      "u2",
      "a2",
    ]);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// SSE 401 — 재수정 P0-2
// ─────────────────────────────────────────────────────────────────────────────

describe("SSE 401 에서 세션·대화 공통 초기화 (재수정 P0-2)", () => {
  it("세션 만료 401 이면 QA 대화와 로그인 세션을 모두 비운다", async () => {
    useQAStore.setState({
      messages: [...PAST_TURN],
      ownerUserId: 7,
      pendingHomeQuestion: "대기 질문",
    });
    useSessionStore.setState({ user: { user_id: 7 } } as never);
    mockStatus(401, { code: "AUTH_SESSION_EXPIRED" });

    const { result } = renderHook(() => useQAStream(), { wrapper });
    await result.current.submit("세션 끊긴 뒤 보낸 질문");

    const qa = useQAStore.getState();
    expect(qa.messages).toEqual([]);
    expect(qa.pendingHomeQuestion).toBeNull();
    expect(qa.ownerUserId).toBeNull();
    expect(useSessionStore.getState().user).toBeNull();
  });

  it("중복 로그인(AUTH_SESSION_SUPERSEDED) 401 도 똑같이 비운다", async () => {
    useQAStore.setState({ messages: [...PAST_TURN], ownerUserId: 7 });
    mockStatus(401, { code: "AUTH_SESSION_SUPERSEDED" });

    const { result } = renderHook(() => useQAStream(), { wrapper });
    await result.current.submit("무효화된 세션의 질문");

    expect(useQAStore.getState().messages).toEqual([]);
    expect(useQAStore.getState().ownerUserId).toBeNull();
  });

  it("코드 없는 401 도 비운다", async () => {
    useQAStore.setState({ messages: [...PAST_TURN], ownerUserId: 7 });
    mockStatus(401, {});

    const { result } = renderHook(() => useQAStream(), { wrapper });
    await result.current.submit("질문");

    expect(useQAStore.getState().messages).toEqual([]);
  });

  it("401 이면 안내를 표시한다", async () => {
    mockStatus(401, { code: "AUTH_SESSION_EXPIRED" });

    const { result } = renderHook(() => useQAStream(), { wrapper });
    await result.current.submit("질문");

    expect(alertShown()).toBe(true);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 맥락 스냅샷 — 재수정 P1-2
// ─────────────────────────────────────────────────────────────────────────────

describe("맥락 스냅샷 (재수정 P1-2)", () => {
  it("답변 메시지에 최초 요청 당시의 history_turn_ids 를 기록한다", async () => {
    fetchEventSourceMock.mockResolvedValue(undefined);
    useQAStore.setState({ messages: [...PAST_TURN] });

    const { result } = renderHook(() => useQAStream(), { wrapper });
    await result.current.submit("그럼 몇 번까지 돼?");

    const messages = useQAStore.getState().messages;
    const assistant = messages[messages.length - 1];
    expect(assistant.role).toBe("assistant");
    expect(assistant.historyTurnIds).toEqual([101]);
  });

  it("첫 질문의 스냅샷은 빈 배열이다 (undefined 가 아니다)", async () => {
    fetchEventSourceMock.mockResolvedValue(undefined);

    const { result } = renderHook(() => useQAStream(), { wrapper });
    await result.current.submit("스케일링 산정 기준");

    const messages = useQAStore.getState().messages;
    expect(messages[messages.length - 1].historyTurnIds).toEqual([]);
  });

  it("호출부가 넘긴 historyTurnIds 를 그대로 전송한다", async () => {
    fetchEventSourceMock.mockResolvedValue(undefined);
    // 화면에는 101·202 두 턴이 있지만, 재시도는 101 만 쓰도록 지시한다.
    useQAStore.setState({ messages: [...PAST_TURN, ...LATER_TURN] });

    const { result } = renderHook(() => useQAStream(), { wrapper });
    await result.current.submit("스케일링 산정 기준", {
      retry: true,
      historyTurnIds: [101],
    });

    const [, options] = fetchEventSourceMock.mock.calls[0];
    const body = JSON.parse((options as { body: string }).body);
    expect(body.history_turn_ids).toEqual([101]);
    expect(body.history_turn_ids).not.toContain(202);
    expect(body.retry).toBe(true);
  });

  it("호출부가 넘긴 목록도 상한(30개)으로 자른다", async () => {
    fetchEventSourceMock.mockResolvedValue(undefined);
    const overflow = Array.from({ length: 35 }, (_, i) => i + 1);

    const { result } = renderHook(() => useQAStream(), { wrapper });
    await result.current.submit("질문", { historyTurnIds: overflow });

    const [, options] = fetchEventSourceMock.mock.calls[0];
    const body = JSON.parse((options as { body: string }).body);
    expect(body.history_turn_ids).toHaveLength(MAX_HISTORY_TURN_IDS);
    expect(body.history_turn_ids[body.history_turn_ids.length - 1]).toBe(35);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 스트림 시작 전 나머지 비정상 상태 — 3차 검수 P1-5
//
// 예전에는 401·429 만 다루고 그 외는 throw 로 떨어져 catch 가
// "인터넷 연결이 끊겨 답변이 중단됐어요" 를 붙였다. 실제 원인(관리자 비상 정지 등)과
// 전혀 다른 문구이고, dropTurn 을 안 타 **빈 답변 말풍선이 영구히 남았다**.
// ─────────────────────────────────────────────────────────────────────────────

const OTHER_ERRORS: Array<[string, number, Record<string, unknown>]> = [
  [
    "503 비상 정지",
    503,
    {
      code: "KILLSWITCH_ACTIVE",
      message: "서비스가 일시 중단되었습니다. 재개 시 알림톡으로 안내드립니다.",
    },
  ],
  [
    "422 질문 길이 초과",
    422,
    { code: "QUESTION_TOO_LONG", message: "질문은 최대 100자까지 입력할 수 있습니다." },
  ],
  ["500 서버 오류", 500, { code: "INTERNAL_ERROR", message: "서버 오류" }],
  ["본문 없는 503", 503, {}],
];

describe("스트림 시작 전 비정상 상태 (3차 검수 P1-5)", () => {
  it.each(OTHER_ERRORS)(
    "%s — 과거 대화는 보존하고 이번 턴만 제거한다",
    async (_label, status, body) => {
      useQAStore.setState({ messages: [...PAST_TURN] });
      mockStatus(status as number, body as Record<string, unknown>);

      const { result } = renderHook(() => useQAStream(), { wrapper });
      await result.current.submit("거절될 질문");

      const messages = useQAStore.getState().messages;
      expect(messages.map((m) => m.id)).toEqual(["u1", "a1"]);
      // 빈 답변 말풍선이 오류 상태로 남지 않는다.
      expect(
        messages.some((m) => m.role === "assistant" && m.content === ""),
      ).toBe(false);
    },
  );

  it.each(OTHER_ERRORS)("%s — 안내를 표시한다", async (_label, status, body) => {
    mockStatus(status as number, body as Record<string, unknown>);

    const { result } = renderHook(() => useQAStream(), { wrapper });
    await result.current.submit("거절될 질문");

    expect(alertShown()).toBe(true);
  });

  it("503 에서는 서버가 보낸 안내 문구를 그대로 쓴다 (인터넷 탓으로 돌리지 않는다)", async () => {
    mockStatus(503, {
      code: "KILLSWITCH_ACTIVE",
      message: "서비스가 일시 중단되었습니다. 재개 시 알림톡으로 안내드립니다.",
    });

    const { result } = renderHook(() => useQAStream(), { wrapper });
    await result.current.submit("질문");

    const alerts = useAlertStore.getState() as unknown as {
      queue?: Array<{ description?: string }>;
      current?: { description?: string };
    };
    const shown = alerts.current ?? alerts.queue?.[0];
    expect(shown?.description).toContain("재개");
    expect(shown?.description).not.toContain("인터넷");
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 토큰 이벤트 방어 — 3차 검수 P2
// ─────────────────────────────────────────────────────────────────────────────

describe("깨진 token 이벤트가 스트림을 죽이지 않는다 (3차 검수 P2)", () => {
  it("delta 가 없거나 문자열이 아니면 건너뛰고 계속 받는다", async () => {
    fetchEventSourceMock.mockImplementation(async (_url: string, opts: never) => {
      const options = opts as unknown as {
        onopen: (r: Response) => Promise<void>;
        onmessage: (ev: { event: string; data: string }) => void;
      };
      await options.onopen({ status: 200, ok: true } as unknown as Response);
      // delta 없음 / 숫자 / null → 전부 무시돼야 한다
      options.onmessage({ event: "token", data: JSON.stringify({}) });
      options.onmessage({ event: "token", data: JSON.stringify({ delta: 42 }) });
      options.onmessage({ event: "token", data: JSON.stringify({ delta: null }) });
      // 그 뒤 정상 토큰은 받아야 한다
      options.onmessage({ event: "token", data: JSON.stringify({ delta: "정상" }) });
      options.onmessage({
        event: "done",
        data: JSON.stringify({ qa_log_id: 9, total_tokens: 1, cost_usd: 0 }),
      });
    });

    const { result } = renderHook(() => useQAStream(), { wrapper });
    await result.current.submit("질문");

    // 스트림이 abort 되지 않았다 = "인터넷 연결이 끊겨…" 안내가 붙지 않았다.
    const assistant = useQAStore
      .getState()
      .messages.find((m) => m.role === "assistant");
    expect(assistant?.errorMessage).toBeUndefined();
  });
});
