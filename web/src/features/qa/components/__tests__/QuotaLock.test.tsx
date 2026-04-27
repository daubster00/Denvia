import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { useQuotaStore } from "@/stores/quota-store";
import { QuotaLock } from "../QuotaLock";

const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

const LOCK_PAYLOAD = {
  reason: "QUOTA_EXCEEDED" as const,
  dailyLimit: 10,
  usedToday: 11,
  resetAt: "2026-04-28T00:00:00+09:00",
  showUpgradePrompt: true,
  showSubscribeButton: true,
};

describe("QuotaLock", () => {
  beforeEach(() => {
    useQuotaStore.setState({ locked: false, payload: null });
    mockPush.mockReset();
  });

  it("locked=false이면 렌더하지 않음", () => {
    const { container } = render(<QuotaLock />);
    expect(container.firstChild).toBeNull();
  });

  it("QUOTA_EXCEEDED 잠금 시 headline + 버튼 2개 렌더", () => {
    useQuotaStore.setState({ locked: true, payload: LOCK_PAYLOAD });
    render(<QuotaLock />);
    expect(screen.getByText(/오늘의 10회를 모두 사용했어요/)).toBeTruthy();
    expect(screen.getByText("내일 다시")).toBeTruthy();
    expect(screen.getByText("Pro로 계속")).toBeTruthy();
  });

  it("show_upgrade_prompt=false이면 [Pro로 계속] 미렌더", () => {
    useQuotaStore.setState({
      locked: true,
      payload: { ...LOCK_PAYLOAD, showUpgradePrompt: false },
    });
    render(<QuotaLock />);
    expect(screen.queryByText("Pro로 계속")).toBeNull();
  });

  it("show_subscribe_button=false이면 [Pro로 계속] 미렌더", () => {
    useQuotaStore.setState({
      locked: true,
      payload: { ...LOCK_PAYLOAD, showSubscribeButton: false },
    });
    render(<QuotaLock />);
    expect(screen.queryByText("Pro로 계속")).toBeNull();
  });

  it("QUOTA_EXCEEDED_INTERNAL_SAFETY_LIMIT — [Pro로 계속] 숨김 + 내부 오류 카피", () => {
    useQuotaStore.setState({
      locked: true,
      payload: {
        reason: "QUOTA_EXCEEDED_INTERNAL_SAFETY_LIMIT",
        dailyLimit: 500,
        usedToday: 501,
        resetAt: null,
        showUpgradePrompt: false,
        showSubscribeButton: false,
      },
    });
    render(<QuotaLock />);
    expect(screen.getByText(/일시적 시스템 보호 제한/)).toBeTruthy();
    expect(screen.queryByText("Pro로 계속")).toBeNull();
    expect(screen.queryByText("내일 다시")).toBeNull();
  });

  it("[내일 다시] 클릭 시 dismiss() 호출 — locked=false", () => {
    useQuotaStore.setState({ locked: true, payload: LOCK_PAYLOAD });
    render(<QuotaLock />);
    fireEvent.click(screen.getByText("내일 다시"));
    expect(useQuotaStore.getState().locked).toBe(false);
  });

  it("[Pro로 계속] 클릭 시 /subscribe로 이동", () => {
    useQuotaStore.setState({ locked: true, payload: LOCK_PAYLOAD });
    render(<QuotaLock />);
    fireEvent.click(screen.getByText("Pro로 계속"));
    expect(mockPush).toHaveBeenCalledWith("/subscribe");
  });

  it("role=alert 속성이 있어 스크린리더에 알림", () => {
    useQuotaStore.setState({ locked: true, payload: LOCK_PAYLOAD });
    render(<QuotaLock />);
    expect(screen.getByRole("alert")).toBeTruthy();
  });
});
