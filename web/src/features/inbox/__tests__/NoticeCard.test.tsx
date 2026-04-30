/** NoticeCard 단위 테스트 — Story 4.5. */

import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { NoticeCard } from "../components/NoticeCard";
import type { InboxItem } from "../types";

function makeItem(overrides: Partial<InboxItem> = {}): InboxItem {
  return {
    message_id: 1,
    type: "notice",
    title: "5월 정기점검",
    body_html_safe: "<p>점검 안내입니다.</p>",
    is_read: false,
    created_at: new Date().toISOString(),
    notice_id: 12,
    popup_id: null,
    ...overrides,
  };
}

describe("NoticeCard", () => {
  it("type=notice → 공지 ARIA label + 제목", () => {
    const onClick = vi.fn();
    render(<NoticeCard item={makeItem({ type: "notice" })} onClick={onClick} />);
    expect(screen.getByLabelText("공지 쪽지 — 5월 정기점검")).toBeDefined();
  });

  it("type=system → 시스템 ARIA label", () => {
    const onClick = vi.fn();
    render(
      <NoticeCard
        item={makeItem({ type: "system", title: "보안 알림" })}
        onClick={onClick}
      />,
    );
    expect(screen.getByLabelText("시스템 쪽지 — 보안 알림")).toBeDefined();
  });

  it("type=billing → 결제 ARIA label", () => {
    const onClick = vi.fn();
    render(
      <NoticeCard
        item={makeItem({ type: "billing", title: "결제 완료" })}
        onClick={onClick}
      />,
    );
    expect(screen.getByLabelText("결제 쪽지 — 결제 완료")).toBeDefined();
  });

  it("클릭 시 onClick 호출", () => {
    const onClick = vi.fn();
    render(<NoticeCard item={makeItem()} onClick={onClick} />);
    fireEvent.click(screen.getByRole("article"));
    expect(onClick).toHaveBeenCalledWith(1);
  });

  it("body_html에서 태그를 제거한 미리보기 표시", () => {
    const onClick = vi.fn();
    render(
      <NoticeCard
        item={makeItem({
          body_html_safe: "<p><strong>중요!</strong> 점검 알림</p>",
        })}
        onClick={onClick}
      />,
    );
    // 미리보기 텍스트는 태그 제거되어야 함
    expect(screen.getByText(/중요! 점검 알림/)).toBeDefined();
  });
});
