import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  render,
  screen,
  fireEvent,
  waitFor,
  cleanup,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const mocks = vi.hoisted(() => ({
  fetchPopups: vi.fn(),
  togglePopupActive: vi.fn(),
  deletePopup: vi.fn(),
  fetchPopupDetail: vi.fn(),
  routerPush: vi.fn(),
}));

vi.mock("@/features/admin-content/api/popup", async () => {
  const actual = await vi.importActual<
    typeof import("@/features/admin-content/api/popup")
  >("@/features/admin-content/api/popup");
  return {
    ...actual,
    fetchPopups: mocks.fetchPopups,
    togglePopupActive: mocks.togglePopupActive,
    deletePopup: mocks.deletePopup,
    fetchPopupDetail: mocks.fetchPopupDetail,
  };
});

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mocks.routerPush }),
}));

import AdminPopupsPage from "../page";

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <AdminPopupsPage />
    </QueryClientProvider>,
  );
}

describe("AdminPopupsPage", () => {
  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("페이지 마운트 시 fetchPopups가 호출되고 헤딩이 노출된다", async () => {
    mocks.fetchPopups.mockResolvedValue({
      items: [],
      page: 1,
      per_page: 20,
      total: 0,
    });
    renderPage();
    expect(screen.getByRole("heading", { name: "팝업 관리" })).toBeDefined();
    await waitFor(() => {
      expect(mocks.fetchPopups).toHaveBeenCalled();
    });
  });

  it("'새 팝업 작성' 링크는 /admin/content/popups/new 로 이동한다", async () => {
    mocks.fetchPopups.mockResolvedValue({
      items: [],
      page: 1,
      per_page: 20,
      total: 0,
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/등록된 팝업이/)).toBeDefined();
    });
    const link = screen.getByRole("link", { name: /새 팝업 작성/ });
    expect((link as HTMLAnchorElement).getAttribute("href")).toBe(
      "/admin/content/popups/new",
    );
  });

  it("아이템이 있을 때 목록 + 페이지네이션이 노출된다", async () => {
    mocks.fetchPopups.mockResolvedValue({
      items: [
        {
          id: 1,
          title: "5월 프로모션",
          display_start: "2026-05-01T00:00:00+09:00",
          display_end: "2026-05-31T23:59:00+09:00",
          target_segment: "all",
          is_active: true,
          link_url: null,
          created_by_admin_id: 1,
          created_at: "2026-04-30T10:00:00+09:00",
          updated_at: "2026-04-30T10:00:00+09:00",
        },
      ],
      page: 1,
      per_page: 20,
      total: 1,
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("5월 프로모션")).toBeDefined();
    });
    expect(screen.getByLabelText("페이지네이션")).toBeDefined();
  });

  it("팝업 제목 클릭 → /admin/content/popups/[id] 로 라우팅된다", async () => {
    mocks.fetchPopups.mockResolvedValue({
      items: [
        {
          id: 42,
          title: "팝업 A",
          display_start: "2026-05-01T00:00:00+09:00",
          display_end: "2026-05-31T23:59:00+09:00",
          target_segment: "all",
          target_device: "both",
          popup_type: "editor",
          display_position: "center",
          display_position_top_px: null,
          display_position_left_px: null,
          image_url: null,
          sort_order: 0,
          is_active: true,
          link_url: null,
          created_by_admin_id: 1,
          created_at: "2026-04-30T10:00:00+09:00",
          updated_at: "2026-04-30T10:00:00+09:00",
        },
      ],
      page: 1,
      per_page: 20,
      total: 1,
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("팝업 A")).toBeDefined();
    });
    fireEvent.click(screen.getByText("팝업 A"));
    expect(mocks.routerPush).toHaveBeenCalledWith(
      "/admin/content/popups/42",
    );
  });
});
