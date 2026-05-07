/** PopupCarousel — Story 7.2 v2 vitest. */

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
  // 세션·로컬 스토리지 초기화 — 이전 테스트의 dismissal이 누수되지 않게.
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
  // 기본 PC 디바이스로 가정.
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
    image_url: null,
    body_html_safe: "<p>본문</p>",
    link_url: null,
    display_end: "2026-12-31T00:00:00+00:00",
    ...overrides,
  };
}

describe("PopupCarousel", () => {
  it("후보 0건 → 모달 미렌더", async () => {
    vi.mocked(fetchActivePopups).mockResolvedValue([]);
    render(<PopupCarousel />, { wrapper: makeWrapper() });
    await waitFor(() => expect(fetchActivePopups).toHaveBeenCalled());
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("후보 1건 → dialog 노출 + indicator 숨김", async () => {
    vi.mocked(fetchActivePopups).mockResolvedValue([makePopup({ popup_id: 10 })]);
    render(<PopupCarousel />, { wrapper: makeWrapper() });
    await waitFor(() => expect(screen.getByRole("dialog")).toBeDefined());
    expect(screen.getByText("테스트 팝업")).toBeDefined();
    // indicator(role=tablist)는 1건일 때 숨김
    expect(screen.queryByRole("tablist")).toBeNull();
  });

  it("후보 2건 → indicator(dots + 1/2) 표시 + 다음 버튼 클릭", async () => {
    vi.mocked(fetchActivePopups).mockResolvedValue([
      makePopup({ popup_id: 10, title: "첫번째" }),
      makePopup({ popup_id: 11, title: "두번째" }),
    ]);
    render(<PopupCarousel />, { wrapper: makeWrapper() });
    await waitFor(() => expect(screen.getByRole("dialog")).toBeDefined());
    expect(screen.getByText("1 / 2")).toBeDefined();
    fireEvent.click(screen.getByLabelText("다음 팝업"));
    await waitFor(() => expect(screen.getByText("2 / 2")).toBeDefined());
  });

  it("'오늘 하루 안보기' 클릭 → localStorage에 만료시각 기록 + 모달 close", async () => {
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

  it("이미 세션에서 본 팝업 → 미노출", async () => {
    window.sessionStorage.setItem("popup_seen_in_session_99", "1");
    vi.mocked(fetchActivePopups).mockResolvedValue([makePopup({ popup_id: 99 })]);
    render(<PopupCarousel />, { wrapper: makeWrapper() });
    await waitFor(() => expect(fetchActivePopups).toHaveBeenCalled());
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
