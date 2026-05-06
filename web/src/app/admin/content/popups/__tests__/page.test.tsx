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

// PopupEditDialog 자체는 별도 테스트 파일에서 다룸 — 페이지 테스트는 mount 여부만.
vi.mock("@/features/admin-content/components/PopupEditDialog", () => ({
  PopupEditDialog: ({
    mode,
    popupId,
  }: {
    mode: "create" | "edit";
    popupId?: number;
  }) => (
    <div data-testid="edit-dialog">
      mode={mode} popupId={popupId ?? "new"}
    </div>
  ),
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

  it("'새 팝업 작성' 버튼 클릭 → PopupEditDialog가 mode=create로 렌더된다", async () => {
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
    fireEvent.click(screen.getByRole("button", { name: /새 팝업 작성/ }));
    expect(screen.getByTestId("edit-dialog").textContent).toContain(
      "mode=create",
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
});
