/** PopupCarousel — 다중 팝업 동시 표시 vitest. */

import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { useSessionStore } from "@/stores/session-store";

vi.mock("@/features/inbox/api", () => ({
  fetchActivePopups: vi.fn(),
}));

const { fetchActivePopups } = await import("@/features/inbox/api");

import { PopupCarousel } from "../components/PopupCarousel";

function makeWrapper() {
  return function wrapper({ children }: { children: ReactNode }) {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

beforeEach(() => {
  vi.mocked(fetchActivePopups).mockReset();
  window.sessionStorage.clear();
  window.localStorage.clear();
  useSessionStore.setState({
    user: {
      user_id: 1,
      email: "u@e.com",
      role: "user",
      subscription_status: "free",
      segment: null,
      years_of_experience: null,
      must_reset_password: false,
      is_social: false,
    },
  });
  window.matchMedia = vi.fn().mockImplementation((q: string) => ({
    matches: false,
    media: q,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }));
});

afterEach(() => {
  window.sessionStorage.clear();
  window.localStorage.clear();
});

function makePopup(overrides: Record<string, unknown> = {}) {
  return {
    popup_id: 1,
    title: "테스트 팝업",
    popup_type: "editor" as const,
    display_position: "center" as const,
    display_position_top_px: null,
    display_position_left_px: null,
    image_url: null,
    body_html_safe: "<p>본문</p>",
    link_url: null,
    display_end: "2026-12-31T00:00:00+00:00",
    ...overrides,
  };
}

describe("PopupCarousel", () => {
  it("후보 0건 → 다이얼로그 미렌더", async () => {
    vi.mocked(fetchActivePopups).mockResolvedValue([]);
    render(<PopupCarousel />, { wrapper: makeWrapper() });
    await waitFor(() => expect(fetchActivePopups).toHaveBeenCalled());
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("후보 1건 → 단일 다이얼로그 노출", async () => {
    vi.mocked(fetchActivePopups).mockResolvedValue([makePopup({ popup_id: 10 })]);
    render(<PopupCarousel />, { wrapper: makeWrapper() });
    await waitFor(() => expect(screen.getByRole("dialog")).toBeDefined());
    expect(screen.getByText("테스트 팝업")).toBeDefined();
  });

  it("후보 3건 → 다이얼로그 3개가 동시에 노출 (캐러셀 없음)", async () => {
    vi.mocked(fetchActivePopups).mockResolvedValue([
      makePopup({ popup_id: 10, title: "첫번째" }),
      makePopup({ popup_id: 11, title: "두번째" }),
      makePopup({ popup_id: 12, title: "세번째" }),
    ]);
    render(<PopupCarousel />, { wrapper: makeWrapper() });
    await waitFor(() => expect(screen.getAllByRole("dialog").length).toBe(3));
    expect(screen.getByText("첫번째")).toBeDefined();
    expect(screen.getByText("두번째")).toBeDefined();
    expect(screen.getByText("세번째")).toBeDefined();
    // 캐러셀 잔여물(indicator/다음 버튼) 없음 확인
    expect(screen.queryByRole("tablist")).toBeNull();
    expect(screen.queryByLabelText("다음 팝업")).toBeNull();
  });

  it("개별 닫기 → 해당 팝업만 사라지고 나머지는 유지", async () => {
    vi.mocked(fetchActivePopups).mockResolvedValue([
      makePopup({ popup_id: 20, title: "유지" }),
      makePopup({ popup_id: 21, title: "닫힐것" }),
    ]);
    render(<PopupCarousel />, { wrapper: makeWrapper() });
    await waitFor(() => expect(screen.getAllByRole("dialog").length).toBe(2));
    // "닫힐것" 다이얼로그의 X 버튼 클릭
    const closeButtons = screen.getAllByLabelText("닫기");
    fireEvent.click(closeButtons[1]);
    await waitFor(() => expect(screen.getAllByRole("dialog").length).toBe(1));
    expect(screen.getByText("유지")).toBeDefined();
    expect(screen.queryByText("닫힐것")).toBeNull();
  });

  it("'오늘 하루 안보기' → 해당 팝업만 localStorage 기록 + 닫힘", async () => {
    vi.mocked(fetchActivePopups).mockResolvedValue([makePopup({ popup_id: 42 })]);
    render(<PopupCarousel />, { wrapper: makeWrapper() });
    await waitFor(() => expect(screen.getByRole("dialog")).toBeDefined());
    fireEvent.click(screen.getByText("오늘 하루 안보기"));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(window.localStorage.getItem("popup_dismissed_until_42")).not.toBeNull();
  });

  it("이미지 타입 → <img> 태그 노출", async () => {
    vi.mocked(fetchActivePopups).mockResolvedValue([
      makePopup({
        popup_id: 7,
        popup_type: "image",
        image_url: "/static/popup-images/abc.png",
        body_html_safe: null,
      }),
    ]);
    render(<PopupCarousel />, { wrapper: makeWrapper() });
    await waitFor(() => expect(screen.getByRole("dialog")).toBeDefined());
    const img = screen.getByRole("img") as HTMLImageElement;
    expect(img.src).toContain("/static/popup-images/abc.png");
  });

  it("'오늘 하루 안보기'로 차단된 팝업 → 미노출", async () => {
    const future = new Date(Date.now() + 60 * 60 * 1000).toISOString();
    window.localStorage.setItem("popup_dismissed_until_99", future);
    vi.mocked(fetchActivePopups).mockResolvedValue([makePopup({ popup_id: 99 })]);
    render(<PopupCarousel />, { wrapper: makeWrapper() });
    await waitFor(() => expect(fetchActivePopups).toHaveBeenCalled());
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
