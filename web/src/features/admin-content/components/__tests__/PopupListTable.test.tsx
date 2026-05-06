import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { PopupListTable } from "../PopupListTable";
import type { PopupListItem } from "@/features/admin-content/api/popup";

function makeItem(overrides: Partial<PopupListItem> = {}): PopupListItem {
  return {
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
    ...overrides,
  };
}

describe("PopupListTable", () => {
  beforeEach(() => cleanup());

  it("아이템이 비어있으면 안내 메시지 노출", () => {
    render(
      <PopupListTable
        items={[]}
        togglingId={null}
        onEdit={() => {}}
        onToggle={() => {}}
        onDelete={() => {}}
      />,
    );
    expect(screen.getByRole("status").textContent).toContain("등록된 팝업이");
  });

  it("아이템 목록 렌더 — 제목/타겟 뱃지/활성 Switch/편집·삭제 버튼", () => {
    render(
      <PopupListTable
        items={[
          makeItem({ id: 1, title: "팝업 A", target_segment: "all" }),
          makeItem({
            id: 2,
            title: "팝업 B",
            target_segment: "doctor",
            is_active: false,
          }),
        ]}
        togglingId={null}
        onEdit={() => {}}
        onToggle={() => {}}
        onDelete={() => {}}
      />,
    );
    expect(screen.getByText("팝업 A")).toBeDefined();
    expect(screen.getByText("팝업 B")).toBeDefined();
    expect(screen.getByText("전체")).toBeDefined();
    expect(screen.getByText("의사")).toBeDefined();
    // Switch는 텍스트도 함께 노출(UX-DR24)
    expect(screen.getAllByRole("switch").length).toBe(2);
    expect(screen.getByLabelText("팝업 A 활성화 토글").textContent).toBe("ON");
    expect(screen.getByLabelText("팝업 B 활성화 토글").textContent).toBe("OFF");
  });

  it("활성 Switch 클릭 → onToggle(id, !is_active) 호출", () => {
    const onToggle = vi.fn();
    render(
      <PopupListTable
        items={[makeItem({ id: 12, is_active: true })]}
        togglingId={null}
        onEdit={() => {}}
        onToggle={onToggle}
        onDelete={() => {}}
      />,
    );
    fireEvent.click(screen.getByRole("switch"));
    expect(onToggle).toHaveBeenCalledWith(12, false);
  });

  it("편집 버튼 클릭 → onEdit(id) 호출", () => {
    const onEdit = vi.fn();
    render(
      <PopupListTable
        items={[makeItem({ id: 7 })]}
        togglingId={null}
        onEdit={onEdit}
        onToggle={() => {}}
        onDelete={() => {}}
      />,
    );
    fireEvent.click(screen.getByText("편집"));
    expect(onEdit).toHaveBeenCalledWith(7);
  });

  it("삭제 버튼 클릭 → onDelete(item) 호출", () => {
    const onDelete = vi.fn();
    const item = makeItem({ id: 9 });
    render(
      <PopupListTable
        items={[item]}
        togglingId={null}
        onEdit={() => {}}
        onToggle={() => {}}
        onDelete={onDelete}
      />,
    );
    fireEvent.click(screen.getByText("삭제"));
    expect(onDelete).toHaveBeenCalledWith(item);
  });

  it("togglingId가 일치하는 row의 Switch는 disabled", () => {
    render(
      <PopupListTable
        items={[
          makeItem({ id: 5, title: "A" }),
          makeItem({ id: 6, title: "B" }),
        ]}
        togglingId={5}
        onEdit={() => {}}
        onToggle={() => {}}
        onDelete={() => {}}
      />,
    );
    expect(
      (screen.getByLabelText("A 활성화 토글") as HTMLButtonElement).disabled,
    ).toBe(true);
    expect(
      (screen.getByLabelText("B 활성화 토글") as HTMLButtonElement).disabled,
    ).toBe(false);
  });
});
