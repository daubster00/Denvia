/** AuthenticatedQAExperience 메인 팝업 마운트 — Story 4.5 (T7). */

import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { useSessionStore } from "@/stores/session-store";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/",
}));

vi.mock("@/components/layout/TopNav", () => ({
  TopNav: () => <header data-testid="topnav-stub" />,
}));

vi.mock("@/components/brand/AdvisoryChip", () => ({
  AdvisoryChip: () => null,
}));

vi.mock("@/features/qa/ChatInput", () => ({
  ChatInput: () => <div data-testid="chat-input-stub" />,
}));

vi.mock("@/features/qa/components/ChatShell", () => ({
  ChatShell: () => null,
}));

vi.mock("@/features/qa/hooks/useQAStream", () => ({
  useQAStream: () => ({ submit: vi.fn(), abort: vi.fn() }),
}));

vi.mock("@/features/qa/hooks/useQuota", () => ({
  useQuota: () => ({ data: undefined }),
}));

vi.mock("@/features/qa/api/events", () => ({
  postClientEvent: vi.fn(),
}));

vi.mock("@/stores/qa-store", () => ({
  useQAStore: (selector: (s: { messages: unknown[]; clearMessages: () => void }) => unknown) =>
    selector({ messages: [], clearMessages: vi.fn() }),
}));

vi.mock("@/features/inbox/api", () => ({
  fetchActivePopup: vi.fn(),
  markPopupSeen: vi.fn(() => Promise.resolve()),
}));

const { fetchActivePopup } = await import("@/features/inbox/api");

import { AuthenticatedQAExperience } from "../QAHomeExperience";

function makeWrapper() {
  return function wrapper({ children }: { children: ReactNode }) {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

beforeEach(() => {
  vi.mocked(fetchActivePopup).mockReset();
  useSessionStore.setState({
    user: {
      user_id: 1,
      email: "u@e.com",
      role: "user",
      subscription_status: "free",
      segment: null,
      years_of_experience: null,
      must_reset_password: false,
    },
  });
});

describe("AuthenticatedQAExperience — Story 4.5 popup mount", () => {
  it("204 응답(null) → PopupModal 미렌더", async () => {
    vi.mocked(fetchActivePopup).mockResolvedValue(null);
    render(<AuthenticatedQAExperience />, { wrapper: makeWrapper() });
    await waitFor(() => expect(fetchActivePopup).toHaveBeenCalled());
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("200 응답 → PopupModal 마운트(role=dialog + 제목 표시)", async () => {
    vi.mocked(fetchActivePopup).mockResolvedValue({
      popup_id: 12,
      title: "신규 서비스 안내",
      body_html_safe: "<p>본문</p>",
      link_url: null,
      display_end: "2026-12-31T00:00:00+00:00",
    });
    render(<AuthenticatedQAExperience />, { wrapper: makeWrapper() });
    await waitFor(() =>
      expect(screen.getByRole("dialog")).toBeDefined(),
    );
    expect(screen.getByText("신규 서비스 안내")).toBeDefined();
  });

  it("닫기 버튼 클릭 시 markPopupSeen 호출", async () => {
    const { markPopupSeen } = await import("@/features/inbox/api");
    vi.mocked(fetchActivePopup).mockResolvedValue({
      popup_id: 99,
      title: "T",
      body_html_safe: "<p>x</p>",
      link_url: null,
      display_end: "2026-12-31T00:00:00+00:00",
    });
    render(<AuthenticatedQAExperience />, { wrapper: makeWrapper() });
    await waitFor(() => expect(screen.getByRole("dialog")).toBeDefined());
    fireEvent.click(screen.getByLabelText("닫기"));
    await waitFor(() => expect(markPopupSeen).toHaveBeenCalledWith(99));
  });
});
