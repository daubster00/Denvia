/**
 * useQAStream 훅 단위 테스트
 *
 * fetchEventSource를 vi.mock으로 모킹.
 * - 토큰 누적 → useQAStore.messages에 반영
 * - error 이벤트 → status='error'
 * - AbortController: 두 번째 submit 시 첫 요청이 abort 신호 수신
 * - Story 2.3: 429 분기 → useQuotaStore.lock + clearMessages
 */

import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useQAStream } from "../useQAStream";
import { useQAStore } from "@/stores/qa-store";
import { useQuotaStore } from "@/stores/quota-store";

// fetchEventSource 모킹
vi.mock("@microsoft/fetch-event-source", () => ({
  fetchEventSource: vi.fn(),
}));

import { fetchEventSource } from "@microsoft/fetch-event-source";

const mockedFetchEventSource = vi.mocked(fetchEventSource);

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

function resetStores() {
  useQAStore.setState({ messages: [] });
  useQuotaStore.setState({ locked: false, payload: null });
}

beforeEach(() => {
  resetStores();
  vi.clearAllMocks();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useQAStream", () => {
  it("submit이 user + assistant 메시지를 즉시 추가한다", async () => {
    mockedFetchEventSource.mockResolvedValue(undefined);

    const { result } = renderHook(() => useQAStream(), { wrapper: makeWrapper() });

    await act(async () => {
      await result.current.submit("임플란트 질문");
    });

    const messages = useQAStore.getState().messages;
    expect(messages).toHaveLength(2);
    expect(messages[0].role).toBe("user");
    expect(messages[0].content).toBe("임플란트 질문");
    expect(messages[1].role).toBe("assistant");
    expect(messages[1].status).toBe("pending");
  });

  it("token 이벤트가 assistant content에 누적된다", async () => {
    mockedFetchEventSource.mockImplementation(async (_url, opts) => {
      opts.onmessage?.({ event: "token", data: '{"delta":"안녕"}', id: "", retry: undefined });
      opts.onmessage?.({ event: "token", data: '{"delta":"하세요"}', id: "", retry: undefined });
      opts.onmessage?.({ event: "done", data: '{"qa_log_id":1,"total_tokens":5,"cost_usd":0,"latency_ms":100,"rule_matched":false}', id: "", retry: undefined });
    });

    const { result } = renderHook(() => useQAStream(), { wrapper: makeWrapper() });

    await act(async () => {
      await result.current.submit("치료비");
    });

    const asst = useQAStore.getState().messages.find((m) => m.role === "assistant");
    expect(asst?.content).toBe("안녕하세요");
    expect(asst?.status).toBe("complete");
    expect(asst?.qaLogId).toBe(1);
  });

  it("error 이벤트가 assistant status를 'error'로 변경한다", async () => {
    mockedFetchEventSource.mockImplementation(async (_url, opts) => {
      opts.onmessage?.({
        event: "error",
        data: '{"code":"OPENAI_TIMEOUT","message":"답변 생성이 일시 지연됩니다."}',
        id: "",
        retry: undefined,
      });
    });

    const { result } = renderHook(() => useQAStream(), { wrapper: makeWrapper() });

    await act(async () => {
      await result.current.submit("질문");
    });

    const asst = useQAStore.getState().messages.find((m) => m.role === "assistant");
    expect(asst?.status).toBe("error");
    expect(asst?.content).toBe("답변 생성이 일시 지연됩니다.");
  });

  it("rule_matched 이벤트가 ruleMatched와 procedureCount를 설정한다", async () => {
    mockedFetchEventSource.mockImplementation(async (_url, opts) => {
      opts.onmessage?.({ event: "rule_matched", data: '{"procedure_count":2}', id: "", retry: undefined });
      opts.onmessage?.({ event: "token", data: '{"delta":"가산 적용 가능합니다."}', id: "", retry: undefined });
      opts.onmessage?.({ event: "done", data: '{"qa_log_id":5,"total_tokens":0,"cost_usd":0,"latency_ms":30,"rule_matched":true}', id: "", retry: undefined });
    });

    const { result } = renderHook(() => useQAStream(), { wrapper: makeWrapper() });

    await act(async () => {
      await result.current.submit("장애인 발치 가산");
    });

    const asst = useQAStore.getState().messages.find((m) => m.role === "assistant");
    expect(asst?.ruleMatched).toBe(true);
    expect(asst?.procedureCount).toBe(2);
  });

  it("두 번째 submit 시 이전 AbortController의 abort가 호출된다", async () => {
    let callCount = 0;

    mockedFetchEventSource.mockImplementation(async (_url, opts) => {
      callCount++;
      if (callCount === 1) {
        return new Promise<void>((_resolve, reject) => {
          const sig = opts.signal;
          if (sig?.aborted) {
            reject(Object.assign(new Error("AbortError"), { name: "AbortError" }));
          } else {
            sig?.addEventListener("abort", () =>
              reject(Object.assign(new Error("AbortError"), { name: "AbortError" }))
            );
          }
        });
      }
      opts.onmessage?.({
        event: "done",
        data: '{"qa_log_id":2,"total_tokens":0,"cost_usd":0,"latency_ms":10,"rule_matched":false}',
        id: "",
        retry: undefined,
      });
    });

    const { result } = renderHook(() => useQAStream(), { wrapper: makeWrapper() });

    act(() => { result.current.submit("첫 번째 질문"); });

    await act(async () => {
      await result.current.submit("두 번째 질문");
    });

    expect(mockedFetchEventSource).toHaveBeenCalledTimes(2);
    const firstCallSignal = (mockedFetchEventSource.mock.calls[0][1] as { signal: AbortSignal }).signal;
    expect(firstCallSignal.aborted).toBe(true);
  }, 10000);

  it("AbortError는 setError를 호출하지 않는다", async () => {
    mockedFetchEventSource.mockRejectedValue(
      Object.assign(new Error("AbortError"), { name: "AbortError" })
    );

    const { result } = renderHook(() => useQAStream(), { wrapper: makeWrapper() });

    await act(async () => {
      await result.current.submit("질문");
    });

    const asst = useQAStore.getState().messages.find((m) => m.role === "assistant");
    expect(asst?.status).toBe("pending");
  });

  // ── Story 2.3: 429 분기 테스트 ────────────────────────────────────────────

  it("429 QUOTA_EXCEEDED → useQuotaStore.lock + clearMessages (AC-7)", async () => {
    mockedFetchEventSource.mockImplementation(async (_url, opts) => {
      const fakeResponse = {
        status: 429,
        ok: false,
        json: async () => ({
          code: "QUOTA_EXCEEDED",
          details: {
            daily_limit: 10,
            used_today: 11,
            reset_at: "2026-04-28T00:00:00+09:00",
            show_upgrade_prompt: true,
            show_subscribe_button: true,
          },
        }),
      } as unknown as Response;
      await (opts as { onopen?: (r: Response) => Promise<void> }).onopen?.(fakeResponse);
    });

    const { result } = renderHook(() => useQAStream(), { wrapper: makeWrapper() });
    await act(async () => {
      await result.current.submit("테스트 질문");
    });

    expect(useQuotaStore.getState().locked).toBe(true);
    expect(useQuotaStore.getState().payload?.reason).toBe("QUOTA_EXCEEDED");
    expect(useQuotaStore.getState().payload?.dailyLimit).toBe(10);
    // 1문 1답 정책: 한도 초과 시 messages 초기화
    expect(useQAStore.getState().messages.length).toBe(0);
  });

  it("429 QUOTA_EXCEEDED_INTERNAL_SAFETY_LIMIT → store.lock with internal reason", async () => {
    mockedFetchEventSource.mockImplementation(async (_url, opts) => {
      const fakeResponse = {
        status: 429,
        ok: false,
        json: async () => ({
          code: "QUOTA_EXCEEDED_INTERNAL_SAFETY_LIMIT",
          details: {
            daily_limit: 500,
            used_today: 501,
            reset_at: null,
            show_upgrade_prompt: false,
            show_subscribe_button: false,
          },
        }),
      } as unknown as Response;
      await (opts as { onopen?: (r: Response) => Promise<void> }).onopen?.(fakeResponse);
    });

    const { result } = renderHook(() => useQAStream(), { wrapper: makeWrapper() });
    await act(async () => {
      await result.current.submit("질문");
    });

    const state = useQuotaStore.getState();
    expect(state.locked).toBe(true);
    expect(state.payload?.reason).toBe("QUOTA_EXCEEDED_INTERNAL_SAFETY_LIMIT");
    expect(state.payload?.showUpgradePrompt).toBe(false);
    expect(state.payload?.showSubscribeButton).toBe(false);
  });

  // ── Story 2.5: abort() 노출 테스트 ──────────────────────────────────────────

  it("abort()가 반환값으로 노출된다", () => {
    const { result } = renderHook(() => useQAStream(), { wrapper: makeWrapper() });
    expect(typeof result.current.abort).toBe("function");
  });

  it("abort() 호출 시 abortRef가 null이 된다 (stale ref 방지)", async () => {
    mockedFetchEventSource.mockImplementation(
      () =>
        new Promise<void>(() => {
          // 영원히 pending — abort로만 종료
        }),
    );

    const { result } = renderHook(() => useQAStream(), { wrapper: makeWrapper() });

    act(() => {
      result.current.submit("질문");
    });

    act(() => {
      result.current.abort();
    });

    // abort 후 두 번째 submit이 새 AbortController로 정상 동작해야 함
    mockedFetchEventSource.mockResolvedValueOnce(undefined);
    await act(async () => {
      await result.current.submit("새 질문");
    });

    expect(mockedFetchEventSource).toHaveBeenCalledTimes(2);
  });

  it("abort() 후 submit 재호출이 정상 동작한다", async () => {
    mockedFetchEventSource.mockImplementation(async (_url, opts) => {
      opts.onmessage?.({
        event: "done",
        data: '{"qa_log_id":10,"total_tokens":0,"cost_usd":0,"latency_ms":5,"rule_matched":false}',
        id: "",
        retry: undefined,
      });
    });

    const { result } = renderHook(() => useQAStream(), { wrapper: makeWrapper() });

    act(() => {
      result.current.abort();
    });

    await act(async () => {
      await result.current.submit("질문");
    });

    const messages = useQAStore.getState().messages;
    expect(messages.length).toBe(2);
    expect(messages[1].status).toBe("complete");
  });

  it("기타 4xx → quotaStore 미잠금 (기존 동작 유지)", async () => {
    mockedFetchEventSource.mockImplementation(async (_url, opts) => {
      const fakeResponse = {
        status: 403,
        ok: false,
        json: async () => ({}),
      } as unknown as Response;
      try {
        await (opts as { onopen?: (r: Response) => Promise<void> }).onopen?.(fakeResponse);
      } catch {
        // 기존 setError 분기
      }
    });

    const { result } = renderHook(() => useQAStream(), { wrapper: makeWrapper() });
    await act(async () => {
      await result.current.submit("질문");
    });

    expect(useQuotaStore.getState().locked).toBe(false);
  });
});
