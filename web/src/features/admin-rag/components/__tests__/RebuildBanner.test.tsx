import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { RebuildBanner } from "../RebuildBanner";
import { useAdminEventsStore } from "@/stores/admin-events-store";

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

// cancelRebuild mock
vi.mock("@/features/admin-rag/api/knowledge", () => ({
  cancelRebuild: vi.fn().mockResolvedValue({}),
}));

// ConfirmDialog mock — open 시 두 버튼 렌더
vi.mock("@/components/layout/ConfirmDialog", () => ({
  ConfirmDialog: ({
    open,
    onConfirm,
    onCancel,
  }: {
    open: boolean;
    onConfirm: () => void;
    onCancel: () => void;
  }) =>
    open ? (
      <div role="dialog">
        <button onClick={onConfirm}>confirm</button>
        <button onClick={onCancel}>cancel</button>
      </div>
    ) : null,
}));

function setProgress(
  progress: number,
  stage: string,
  status?: string,
  error?: string,
  jobId = 1,
) {
  useAdminEventsStore.setState({
    rebuildProgress: { type: "rag_rebuild_progress", job_id: jobId, progress, stage, status, error },
    activeJobId: jobId,
  });
}

beforeEach(() => {
  useAdminEventsStore.setState({
    rebuildProgress: null,
    activeJobId: null,
    budgetWarning: null,
    killswitchStatus: null,
  });
  sessionStorage.clear();
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe("RebuildBanner", () => {
  it("rebuildProgress null → 배너 미렌더", () => {
    render(<RebuildBanner />, { wrapper });
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("progress=45, stage=embedding → 메시지 렌더", () => {
    act(() => setProgress(45, "embedding"));
    render(<RebuildBanner />, { wrapper });
    expect(screen.getByRole("status")).toBeTruthy();
    expect(screen.getByText(/재빌드 중 \(45%\)/)).toBeTruthy();
    expect(screen.getByText(/embedding stage/)).toBeTruthy();
  });

  it("[취소] 클릭 → ConfirmDialog 열림", () => {
    act(() => setProgress(45, "embedding"));
    render(<RebuildBanner />, { wrapper });
    fireEvent.click(screen.getByRole("button", { name: "취소" }));
    expect(screen.getByRole("dialog")).toBeTruthy();
  });

  it("ConfirmDialog confirm → cancelRebuild 호출 + 배너 사라짐", async () => {
    const { cancelRebuild } = await import("@/features/admin-rag/api/knowledge");
    act(() => setProgress(45, "embedding"));
    render(<RebuildBanner />, { wrapper });

    fireEvent.click(screen.getByRole("button", { name: "취소" }));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "confirm" }));
    });

    expect(cancelRebuild).toHaveBeenCalledWith(1);
    // act() above flushed handleCancel → setRebuildProgress(null); no waitFor needed
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("[숨기기] 클릭 → 배너 사라짐 + sessionStorage 세팅", () => {
    act(() => setProgress(45, "embedding"));
    render(<RebuildBanner />, { wrapper });
    fireEvent.click(screen.getByRole("button", { name: "숨기기" }));
    expect(screen.queryByRole("status")).toBeNull();
    expect(sessionStorage.getItem("rebuild_banner_hidden")).toBe("1");
  });

  it("progress=100, status=success → Toast + 배너 사라짐", async () => {
    act(() => setProgress(45, "embedding"));
    const { rerender } = render(<RebuildBanner />, { wrapper });

    // wrap in act so useEffect (setToastMsg + setRebuildProgress(null)) fires before assertion
    await act(async () => {
      setProgress(100, "done", "success");
      rerender(<RebuildBanner />, { wrapper });
    });

    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.getByText(/재빌드 완료/)).toBeTruthy();
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("stage=failed → Toast + 배너 사라짐", async () => {
    act(() => setProgress(45, "embedding"));
    const { rerender } = render(<RebuildBanner />, { wrapper });

    // wrap in act so useEffect (setToastMsg + setRebuildProgress(null)) fires before assertion
    await act(async () => {
      setProgress(0, "failed", "failed", "디스크 오류");
      rerender(<RebuildBanner />, { wrapper });
    });

    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.getByText(/재빌드 실패/)).toBeTruthy();
    expect(screen.getByText(/디스크 오류/)).toBeTruthy();
    expect(screen.queryByRole("status")).toBeNull();
  });
});
