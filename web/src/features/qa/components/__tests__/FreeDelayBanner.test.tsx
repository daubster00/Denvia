import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { FreeDelayBanner } from "../FreeDelayBanner";

const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

const BANNER_KEY = "denvia.free_delay_banner_seen";

describe("FreeDelayBanner", () => {
  beforeEach(() => {
    localStorage.removeItem(BANNER_KEY);
    mockPush.mockReset();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    localStorage.removeItem(BANNER_KEY);
  });

  it("show=false이면 렌더하지 않음", () => {
    const { container } = render(<FreeDelayBanner show={false} />);
    expect(container.firstChild).toBeNull();
  });

  it("show=true + 미열람이면 배너 표시", () => {
    render(<FreeDelayBanner show={true} />);
    expect(screen.getByText(/무료 플랜은 응답이 조금 느려요/)).toBeTruthy();
  });

  it("이미 localStorage 플래그 있으면 표시 안 함", () => {
    localStorage.setItem(BANNER_KEY, "1");
    const { container } = render(<FreeDelayBanner show={true} />);
    expect(container.firstChild).toBeNull();
  });

  it("X 버튼 클릭 시 닫힘 + localStorage 저장", () => {
    render(<FreeDelayBanner show={true} />);
    fireEvent.click(screen.getByRole("button", { name: "배너 닫기" }));
    expect(screen.queryByText(/무료 플랜/)).toBeNull();
    expect(localStorage.getItem(BANNER_KEY)).toBe("1");
  });

  it("15초 후 자동 fade + localStorage 저장", async () => {
    render(<FreeDelayBanner show={true} />);
    expect(screen.getByText(/무료 플랜/)).toBeTruthy();
    act(() => {
      vi.advanceTimersByTime(15_001);
    });
    expect(screen.queryByText(/무료 플랜/)).toBeNull();
    expect(localStorage.getItem(BANNER_KEY)).toBe("1");
  });

  it("[Pro로 즉시 답변받기] 클릭 시 /subscribe 이동", () => {
    render(<FreeDelayBanner show={true} />);
    fireEvent.click(screen.getByText(/Pro로 즉시 답변받기/));
    expect(mockPush).toHaveBeenCalledWith("/subscribe");
  });
});
