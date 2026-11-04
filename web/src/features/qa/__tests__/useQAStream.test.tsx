/**
 * useQAStream — 요청 페이로드와 한도 거절 처리. 2026-11-03 검수 P0-2 · P1-5.
 *
 * 고정하는 것:
 *   - 요청 본문에는 `history_turn_ids`(서버 발급 식별자)만 담기고, 과거 답변 문자열은
 *     어디에도 들어가지 않는다.
 *   - `retry` 플래그가 그대로 전달된다(전송 실패 답변 재생 게이팅용).
 *   - 한도 거절(429)에서 **과거 정상 대화는 보존**되고 이번 거절된 턴만 사라진다.
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

// SSE 호출 가로채기 — 실제 네트워크는 쓰지 않는다.
const fetchEventSourceMock = vi.fn();
vi.mock("@microsoft/fetch-event-source", () => ({
  fetchEventSource: (...args: unknown[]) => fetchEventSourceMock(...args),
}));

import { useQAStream } from "@/features/qa/hooks/useQAStream";
import { useQAStore } from "@/stores/qa-store";
import { useAlertStore } from "@/stores/alert-store";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const PAST_TURN = [
  {
    id: "u1",
    role: "user" as const,
    content: "스케일링 산정 기준",
    status: "complete" as const,
    timestamp: "2026-01-01T00:00:00.000Z",
  },
  {
    id: "a1",
    role: "assistant" as const,
    content: "3분의1악당 1회입니다.",
    status: "complete" as const,
    qaLogId: 101,
    timestamp: "2026-01-01T00:00:00.000Z",
  },
];

beforeEach(() => {
  vi.clearAllMocks();
  useQAStore.setState({ messages: [], pendingHomeQuestion: null, ownerUserId: null });
  useAlertStore.setState({ queue: [] } as never);
});

describe("요청 페이로드 (검수 P0-2)", () => {
  it("과거 답변 문자열 대신 qa_log_id 목록을 보낸다", async () => {
    fetchEventSourceMock.mockResolvedValue(undefined);
    useQAStore.setState({ messages: [...PAST_TURN] });

    const { result } = renderHook(() => useQAStream(), { wrapper });
    await result.current.submit("그럼 몇 번까지 돼?");

    const [, options] = fetchEventSourceMock.mock.calls[0];
    const body = JSON.parse((options as { body: string }).body);

    expect(body.history_turn_ids).toEqual([101]);
    expect(body).not.toHaveProperty("history");
    expect(JSON.stringify(body)).not.toContain("3분의1악당");
    expect(body.retry).toBe(false);
  });

  it("다시 시도로 보낸 질문은 retry=true 로 전달된다 (검수 P0-1)", async () => {
    fetchEventSourceMock.mockResolvedValue(undefined);
    const { result } = renderHook(() => useQAStream(), { wrapper });
    await result.current.submit("스케일링 산정 기준", { retry: true });

    const [, options] = fetchEventSourceMock.mock.calls[0];
    expect(JSON.parse((options as { body: string }).body).retry).toBe(true);
  });
});

describe("한도 거절(429) 처리 (검수 P1-5)", () => {
  it("과거 정상 대화는 보존하고 거절된 이번 턴만 제거한다", async () => {
    useQAStore.setState({ messages: [...PAST_TURN] });

    // onopen 에서 429 를 돌려주는 SSE 대역.
    fetchEventSourceMock.mockImplementation(async (_url: string, opts: never) => {
      const options = opts as unknown as {
        onopen: (r: Response) => Promise<void>;
      };
      await options.onopen({
        status: 429,
        ok: false,
        json: async () => ({
          code: "QUOTA_EXCEEDED",
          details: { daily_limit: 10, show_subscribe_button: true },
        }),
      } as unknown as Response);
    });

    const { result } = renderHook(() => useQAStream(), { wrapper });
    await result.current.submit("오늘 11번째 질문");

    const messages = useQAStore.getState().messages;
    // 과거 질문·답변 1쌍은 그대로 남는다 (예전에는 clearMessages 로 전부 지웠다).
    expect(messages.map((m) => m.id)).toEqual(["u1", "a1"]);
  });

  it("거절되면 안내 팝업을 띄운다", async () => {
    fetchEventSourceMock.mockImplementation(async (_url: string, opts: never) => {
      const options = opts as unknown as {
        onopen: (r: Response) => Promise<void>;
      };
      await options.onopen({
        status: 429,
        ok: false,
        json: async () => ({
          code: "QUOTA_EXCEEDED",
          details: { daily_limit: 10, show_subscribe_button: true },
        }),
      } as unknown as Response);
    });

    const { result } = renderHook(() => useQAStream(), { wrapper });
    await result.current.submit("오늘 11번째 질문");

    const alerts = useAlertStore.getState() as unknown as {
      queue?: unknown[];
      current?: unknown;
    };
    const shown = alerts.queue?.length || alerts.current ? true : false;
    expect(shown).toBe(true);
  });
});
