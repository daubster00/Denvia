/** InboxList 통합 테스트 — Story 4.5. */

import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { InboxList } from "../components/InboxList";
import type { InboxListResponse } from "../types";

vi.mock("../api", () => ({
  fetchInbox: vi.fn(),
  markInboxRead: vi.fn(() => Promise.resolve()),
  markAllInboxRead: vi.fn(() => Promise.resolve({ updated_count: 1 })),
  deleteInboxMessage: vi.fn(() => Promise.resolve()),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/inbox",
  useSearchParams: () => new URLSearchParams(),
}));

const { fetchInbox, markAllInboxRead } = await import("../api");

function makeWrapper() {
  return function wrapper({ children }: { children: ReactNode }) {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

const empty: InboxListResponse = {
  items: [],
  page: 1,
  per_page: 20,
  total: 0,
  unread_count: 0,
};

const oneItem: InboxListResponse = {
  items: [
    {
      message_id: 1,
      type: "notice",
      title: "공지 1",
      body_html_safe: "<p>본문</p>",
      is_read: false,
      created_at: new Date().toISOString(),
      notice_id: 10,
      popup_id: null,
      inquiry_id: null,
    },
  ],
  page: 1,
  per_page: 20,
  total: 1,
  unread_count: 1,
};

beforeEach(() => {
  vi.mocked(fetchInbox).mockReset();
  vi.mocked(markAllInboxRead).mockClear();
});

describe("InboxList", () => {
  it("total=0 → EmptyState '아직 받은 쪽지가 없어요'", async () => {
    vi.mocked(fetchInbox).mockResolvedValue(empty);
    render(<InboxList filter="all" />, { wrapper: makeWrapper() });
    await waitFor(() =>
      expect(screen.getByText(/아직 받은 쪽지가 없어요/)).toBeDefined(),
    );
  });

  it("API 실패 → ErrorState + 새로고침 버튼", async () => {
    vi.mocked(fetchInbox).mockRejectedValue(new Error("boom"));
    render(<InboxList filter="all" />, { wrapper: makeWrapper() });
    await waitFor(
      () => expect(screen.getByRole("alert")).toBeDefined(),
      { timeout: 3000 },
    );
    expect(screen.getByRole("button", { name: /새로고침/ })).toBeDefined();
  });

  it("1건 응답 → 카드 1개 + 페이지네이션 1/1", async () => {
    vi.mocked(fetchInbox).mockResolvedValue(oneItem);
    render(<InboxList filter="all" />, { wrapper: makeWrapper() });
    await waitFor(() => expect(screen.getByText("공지 1")).toBeDefined());
    expect(screen.getByText("1 / 1")).toBeDefined();
  });

  it("이전 버튼은 page=1에서 disabled", async () => {
    vi.mocked(fetchInbox).mockResolvedValue(oneItem);
    render(<InboxList filter="all" />, { wrapper: makeWrapper() });
    await waitFor(() => expect(screen.getByText("공지 1")).toBeDefined());
    const prev = screen.getByRole("button", { name: "이전" });
    expect((prev as HTMLButtonElement).disabled).toBe(true);
  });

  // ── #118: 전체읽음 버튼 ────────────────────────────────────────────────

  it("#118: 안읽은 쪽지가 있으면 전체읽음 버튼이 노출된다", async () => {
    vi.mocked(fetchInbox).mockResolvedValue(oneItem);
    render(<InboxList filter="all" />, { wrapper: makeWrapper() });
    await waitFor(() => expect(screen.getByText("공지 1")).toBeDefined());
    expect(screen.getByRole("button", { name: "전체읽음" })).toBeDefined();
  });

  it("#118: 안읽은 쪽지가 없으면 전체읽음 버튼이 노출되지 않는다", async () => {
    vi.mocked(fetchInbox).mockResolvedValue({
      ...oneItem,
      items: [{ ...oneItem.items[0], is_read: true }],
      unread_count: 0,
    });
    render(<InboxList filter="all" />, { wrapper: makeWrapper() });
    await waitFor(() => expect(screen.getByText("공지 1")).toBeDefined());
    expect(screen.queryByRole("button", { name: "전체읽음" })).toBeNull();
  });

  it("#118: 전체읽음 클릭 → API 호출 + 목록 invalidate(재조회)", async () => {
    vi.mocked(fetchInbox)
      .mockResolvedValueOnce(oneItem)
      .mockResolvedValue({
        ...oneItem,
        items: [{ ...oneItem.items[0], is_read: true }],
        unread_count: 0,
      });
    render(<InboxList filter="all" />, { wrapper: makeWrapper() });
    await waitFor(() => expect(screen.getByText("공지 1")).toBeDefined());

    fireEvent.click(screen.getByRole("button", { name: "전체읽음" }));
    await waitFor(() =>
      expect(markAllInboxRead).toHaveBeenCalledTimes(1),
    );
    // invalidate → 재조회 응답(unread_count=0)이 반영되어 버튼이 사라진다.
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "전체읽음" })).toBeNull(),
    );
    expect(vi.mocked(fetchInbox).mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it("per_page 변경 시 page=1로 reset되고 fetch 재호출", async () => {
    vi.mocked(fetchInbox).mockResolvedValue(oneItem);
    render(<InboxList filter="all" />, { wrapper: makeWrapper() });
    await waitFor(() => expect(screen.getByText("공지 1")).toBeDefined());
    fireEvent.change(screen.getByLabelText("페이지당 쪽지 수"), {
      target: { value: "50" },
    });
    await waitFor(() => {
      const calls = vi.mocked(fetchInbox).mock.calls;
      expect(calls.some(([p, pp]) => p === 1 && pp === 50)).toBe(true);
    });
  });
});
