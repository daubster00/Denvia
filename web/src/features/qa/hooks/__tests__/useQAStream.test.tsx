/**
 * useQAStream 훅 단위 테스트
 *
 * fetchEventSource를 vi.mock으로 모킹.
 * - 토큰 누적 → useQAStore.messages에 반영
 * - error 이벤트 → status='error'
 * - AbortController: 두 번째 submit 시 첫 요청이 abort 신호 수신
 * - Story 2.3: 429 분기 → useAlertStore.show + clearMessages (글로벌 AppAlert 모달)
 */

import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useQAStream } from "../useQAStream";
import { useQAStore } from "@/stores/qa-store";
import { useAlertStore } from "@/stores/alert-store";

// fetchEventSource 모킹
vi.mock("@microsoft/fetch-event-source", () => ({
  fetchEventSource: vi.fn(),
}));

// next/navigation useRouter 모킹 — useQAStream 이 'Pro로 계속' 버튼 onClick 에서 사용
const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush, replace: vi.fn() }),
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
  useAlertStore.setState({ current: null });
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
    // #141: 안내 문구는 errorMessage 로 가고 content(부분 답변)는 건드리지 않는다.
    expect(asst?.errorMessage).toBe("답변 생성이 일시 지연됩니다.");
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

  it("429 QUOTA_EXCEEDED → useAlertStore.show(warning) + clearMessages (AC-7)", async () => {
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

    const alert = useAlertStore.getState().current;
    expect(alert).not.toBeNull();
    expect(alert?.level).toBe("warning");
    expect(alert?.title).toBe("오늘의 10회를 모두 사용했어요.");
    expect(alert?.dedupeKey).toBe("QUOTA_EXCEEDED");
    expect(alert?.actions?.map((a) => a.label)).toEqual(["내일 다시", "Pro로 계속"]);
    // "Pro로 계속" 클릭 시 router.push("/subscribe")
    alert?.actions?.find((a) => a.label === "Pro로 계속")?.onClick?.();
    expect(mockPush).toHaveBeenCalledWith("/subscribe");
    // 1문 1답 정책: 한도 초과 시 messages 초기화
    expect(useQAStore.getState().messages.length).toBe(0);
  });

  it("429 QUOTA_EXCEEDED_INTERNAL_SAFETY_LIMIT → 단일 '확인' 버튼 + 고객문의 안내", async () => {
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

    const alert = useAlertStore.getState().current;
    expect(alert?.title).toBe("일시적 시스템 보호 제한에 도달했습니다.");
    expect(alert?.description).toBe("고객문의로 연락주세요.");
    expect(alert?.actions?.map((a) => a.label)).toEqual(["확인"]);
  });

  it("show_subscribe_button=false → 'Pro로 계속' 버튼 미노출 ('내일 다시'만)", async () => {
    mockedFetchEventSource.mockImplementation(async (_url, opts) => {
      const fakeResponse = {
        status: 429,
        ok: false,
        json: async () => ({
          code: "QUOTA_EXCEEDED",
          details: {
            daily_limit: 10,
            used_today: 11,
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

    const alert = useAlertStore.getState().current;
    expect(alert?.actions?.map((a) => a.label)).toEqual(["내일 다시"]);
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

  // 2026-11-03 3차 검수 P1-5 로 **계약이 바뀌었다.**
  //
  // 예전: 401·429 외의 비정상 응답은 throw 로 떨어져 catch 가
  //       "인터넷 연결이 끊겨 답변이 중단됐어요" 를 붙였고, 알림은 띄우지 않았다.
  // 문제: 그 문구는 실제 원인과 전혀 다르다. 특히 503 KILLSWITCH_ACTIVE(관리자가
  //       서비스를 일시 중단)와 422 QUESTION_TOO_LONG 은 서버가 정확한 안내 문구를
  //       주는데 그게 버려지고 **사용자 탓으로 읽히는 문구**가 나갔다. 게다가
  //       dropTurn 을 타지 않아 빈 답변 말풍선이 누적 대화에 영구히 남았다.
  // 지금: 스트림 시작 전 비정상 응답은 **상태코드와 무관하게** 서버 문구로 안내하고
  //       이번 턴만 걷어낸다(과거 정상 대화는 보존).
  it("기타 4xx → 서버 문구로 안내하고 이번 턴만 제거한다 (3차 검수 P1-5)", async () => {
    mockedFetchEventSource.mockImplementation(async (_url, opts) => {
      const fakeResponse = {
        status: 403,
        ok: false,
        json: async () => ({ code: "FORBIDDEN", message: "권한이 없습니다." }),
      } as unknown as Response;
      await (opts as { onopen?: (r: Response) => Promise<void> }).onopen?.(
        fakeResponse,
      );
    });

    const { result } = renderHook(() => useQAStream(), { wrapper: makeWrapper() });
    await act(async () => {
      await result.current.submit("질문");
    });

    // 안내가 뜬다 — 그리고 서버 문구를 그대로 쓴다.
    const alert = useAlertStore.getState().current;
    expect(alert).not.toBeNull();
    expect(alert?.description).toBe("권한이 없습니다.");
    // 빈 답변 말풍선이 남지 않는다 (이번 턴만 제거).
    expect(useQAStore.getState().messages).toEqual([]);
  });

  it("503 비상 정지는 '인터넷 끊김' 으로 보이지 않는다 (3차 검수 P1-5)", async () => {
    mockedFetchEventSource.mockImplementation(async (_url, opts) => {
      const fakeResponse = {
        status: 503,
        ok: false,
        json: async () => ({
          code: "KILLSWITCH_ACTIVE",
          message: "서비스가 일시 중단되었습니다. 재개 시 알림톡으로 안내드립니다.",
        }),
      } as unknown as Response;
      await (opts as { onopen?: (r: Response) => Promise<void> }).onopen?.(
        fakeResponse,
      );
    });

    const { result } = renderHook(() => useQAStream(), { wrapper: makeWrapper() });
    await act(async () => {
      await result.current.submit("질문");
    });

    const alert = useAlertStore.getState().current;
    expect(alert?.description).toContain("재개");
    expect(alert?.description).not.toContain("인터넷");
    // 어떤 메시지에도 "인터넷 연결이 끊겨" 안내가 붙지 않는다.
    expect(
      useQAStore
        .getState()
        .messages.some((m) => (m.errorMessage ?? "").includes("인터넷")),
    ).toBe(false);
  });
});
