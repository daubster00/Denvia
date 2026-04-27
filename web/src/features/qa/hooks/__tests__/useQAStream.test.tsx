/**
 * useQAStream 훅 단위 테스트
 *
 * msw 2.x SSE 지원을 활용해 fetchEventSource를 모킹한다.
 * - 토큰 누적 → useQAStore.messages에 반영
 * - error 이벤트 → status='error'
 * - AbortController: 두 번째 submit 시 첫 요청이 abort 신호 수신
 */

import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useQAStream } from "../useQAStream";
import { useQAStore } from "@/stores/qa-store";

// fetchEventSource 모킹
vi.mock("@microsoft/fetch-event-source", () => ({
  fetchEventSource: vi.fn(),
}));

import { fetchEventSource } from "@microsoft/fetch-event-source";

const mockedFetchEventSource = vi.mocked(fetchEventSource);

function resetStore() {
  useQAStore.setState({ messages: [] });
}

beforeEach(() => {
  resetStore();
  vi.clearAllMocks();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useQAStream", () => {
  it("submit이 user + assistant 메시지를 즉시 추가한다", async () => {
    mockedFetchEventSource.mockResolvedValue(undefined);

    const { result } = renderHook(() => useQAStream());

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

    const { result } = renderHook(() => useQAStream());

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

    const { result } = renderHook(() => useQAStream());

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

    const { result } = renderHook(() => useQAStream());

    await act(async () => {
      await result.current.submit("장애인 발치 가산");
    });

    const asst = useQAStore.getState().messages.find((m) => m.role === "assistant");
    expect(asst?.ruleMatched).toBe(true);
    expect(asst?.procedureCount).toBe(2);
  });

  it("두 번째 submit 시 이전 AbortController의 abort가 호출된다", async () => {
    const abortSpy = vi.fn();
    let callCount = 0;

    // 첫 번째 호출은 AbortController를 스파이, 두 번째 호출은 바로 완료
    mockedFetchEventSource.mockImplementation(async (_url, opts) => {
      callCount++;
      if (callCount === 1) {
        // 첫 번째는 signal abort를 대기하다가 AbortError 발생 (abort 시 즉시 throw)
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
      // 두 번째 호출은 즉시 done
      opts.onmessage?.({
        event: "done",
        data: '{"qa_log_id":2,"total_tokens":0,"cost_usd":0,"latency_ms":10,"rule_matched":false}',
        id: "",
        retry: undefined,
      });
    });

    const { result } = renderHook(() => useQAStream());

    // 첫 번째 submit 비동기 시작 (기다리지 않음)
    const firstPromise = act(() => { result.current.submit("첫 번째 질문"); });

    // 두 번째 submit 즉시 실행 → 첫 번째 abort
    await act(async () => {
      await result.current.submit("두 번째 질문");
    });

    // fetchEventSource가 두 번 호출됨
    expect(mockedFetchEventSource).toHaveBeenCalledTimes(2);
    // 첫 번째 signal은 abort됨
    const firstCallSignal = (mockedFetchEventSource.mock.calls[0][1] as any).signal as AbortSignal;
    expect(firstCallSignal.aborted).toBe(true);
  }, 10000);

  it("AbortError는 setError를 호출하지 않는다", async () => {
    mockedFetchEventSource.mockRejectedValue(
      Object.assign(new Error("AbortError"), { name: "AbortError" })
    );

    const { result } = renderHook(() => useQAStream());

    await act(async () => {
      await result.current.submit("질문");
    });

    const asst = useQAStore.getState().messages.find((m) => m.role === "assistant");
    // AbortError면 setError 호출 안 됨 → status는 pending 유지
    expect(asst?.status).toBe("pending");
  });
});
