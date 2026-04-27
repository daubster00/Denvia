import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, fireEvent, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AnswerFeedback } from "../AnswerFeedback";

vi.mock("@/features/qa/api/qa-feedback", () => ({
  submitFeedback: vi.fn(),
}));

import { submitFeedback } from "@/features/qa/api/qa-feedback";

const mockSubmitFeedback = submitFeedback as ReturnType<typeof vi.fn>;

function renderWithQuery(ui: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>{ui}</QueryClientProvider>
  );
}

describe("AnswerFeedback", () => {
  beforeEach(() => {
    mockSubmitFeedback.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  // ──── 렌더 기본 검증 ────

  it("qaLogId=1이면 두 버튼 렌더", () => {
    renderWithQuery(<AnswerFeedback qaLogId={1} />);
    expect(screen.getByRole("button", { name: "도움이 됐어요" })).toBeDefined();
    expect(screen.getByRole("button", { name: "도움이 안 됐어요" })).toBeDefined();
  });

  it("컨테이너에 aria-label='답변 피드백' 있음", () => {
    renderWithQuery(<AnswerFeedback qaLogId={1} />);
    expect(screen.getByLabelText("답변 피드백")).toBeDefined();
  });

  it("초기 상태 — 두 버튼 모두 aria-pressed=false", () => {
    renderWithQuery(<AnswerFeedback qaLogId={1} />);
    const thumbUp = screen.getByRole("button", { name: "도움이 됐어요" });
    const thumbDown = screen.getByRole("button", { name: "도움이 안 됐어요" });
    expect(thumbUp.getAttribute("aria-pressed")).toBe("false");
    expect(thumbDown.getAttribute("aria-pressed")).toBe("false");
  });

  // ──── 성공 경로 ────

  it("👍 클릭 시 submitFeedback(1, 'good') 호출", async () => {
    mockSubmitFeedback.mockResolvedValue({
      qa_log_id: 1,
      rating: "good",
      change_count: 0,
      action: "created",
    });
    renderWithQuery(<AnswerFeedback qaLogId={1} />);
    fireEvent.click(screen.getByRole("button", { name: "도움이 됐어요" }));
    await waitFor(() => expect(mockSubmitFeedback).toHaveBeenCalledWith(1, "good"));
  });

  it("성공 응답 후 👍 aria-pressed=true, 👎 aria-pressed=false", async () => {
    mockSubmitFeedback.mockResolvedValue({
      qa_log_id: 1,
      rating: "good",
      change_count: 0,
      action: "created",
    });
    renderWithQuery(<AnswerFeedback qaLogId={1} />);
    fireEvent.click(screen.getByRole("button", { name: "도움이 됐어요" }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "도움이 됐어요" }).getAttribute("aria-pressed")).toBe("true");
    });
    expect(screen.getByRole("button", { name: "도움이 안 됐어요" }).getAttribute("aria-pressed")).toBe("false");
  });

  // ──── 전송 중 disabled ────

  it("전송 중 두 버튼 모두 disabled=true (중복 클릭 방지)", async () => {
    let resolvePromise!: (v: unknown) => void;
    mockSubmitFeedback.mockReturnValue(new Promise((r) => { resolvePromise = r; }));

    renderWithQuery(<AnswerFeedback qaLogId={1} />);
    fireEvent.click(screen.getByRole("button", { name: "도움이 됐어요" }));

    await waitFor(() => {
      expect((screen.getByRole("button", { name: "도움이 됐어요" }) as HTMLButtonElement).disabled).toBe(true);
      expect((screen.getByRole("button", { name: "도움이 안 됐어요" }) as HTMLButtonElement).disabled).toBe(true);
    });

    // 정리 — pending promise 해소
    act(() => {
      resolvePromise({ qa_log_id: 1, rating: "good", change_count: 0, action: "created" });
    });
  });

  // ──── 실패 경로 ────

  it("실패 응답(기타 오류) → 인라인 에러 텍스트 노출", async () => {
    const err = new Error("server error");
    (err as { status?: number }).status = 500;
    mockSubmitFeedback.mockRejectedValue(err);

    renderWithQuery(<AnswerFeedback qaLogId={1} />);
    fireEvent.click(screen.getByRole("button", { name: "도움이 됐어요" }));

    await waitFor(() => {
      expect(screen.getByText(/평가 전송에 실패했습니다/)).toBeDefined();
    });
    expect(screen.getByRole("status")).toBeDefined();
  });

  it("실패 응답(QA_LOG_NOT_FOUND) → 전용 에러 문구 노출", async () => {
    const err = new Error("not found");
    (err as { code?: string }).code = "QA_LOG_NOT_FOUND";
    (err as { status?: number }).status = 404;
    mockSubmitFeedback.mockRejectedValue(err);

    renderWithQuery(<AnswerFeedback qaLogId={1} />);
    fireEvent.click(screen.getByRole("button", { name: "도움이 됐어요" }));

    await waitFor(() => {
      expect(screen.getByText(/평가할 수 없는 답변입니다/)).toBeDefined();
    });
  });

  it("인라인 에러 영역 role=status + aria-live=polite", async () => {
    const err = new Error("server error");
    (err as { status?: number }).status = 500;
    mockSubmitFeedback.mockRejectedValue(err);

    renderWithQuery(<AnswerFeedback qaLogId={1} />);
    fireEvent.click(screen.getByRole("button", { name: "도움이 됐어요" }));

    await waitFor(() => {
      const status = screen.getByRole("status");
      expect(status.getAttribute("aria-live")).toBe("polite");
    });
  });

  // ──── 타이머: 3초 후 fade ────

  it("에러 메시지는 3초 후 사라짐", async () => {
    // fake timer를 렌더 전에 설정하여 onError의 setTimeout도 제어
    vi.useFakeTimers();

    const err = new Error("server error");
    (err as { status?: number }).status = 500;
    mockSubmitFeedback.mockRejectedValue(err);

    renderWithQuery(<AnswerFeedback qaLogId={1} />);
    fireEvent.click(screen.getByRole("button", { name: "도움이 됐어요" }));

    // promise chain 플러시 (microtask)
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(screen.getByText(/평가 전송에 실패했습니다/)).toBeDefined();

    // 3초 경과
    act(() => { vi.advanceTimersByTime(3001); });

    expect(screen.queryByText(/평가 전송에 실패했습니다/)).toBeNull();
  });
});
