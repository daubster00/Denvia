import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { AuditDiffDrawer } from "../components/AuditDiffDrawer";
import type { AuditLogItem } from "@/features/admin-users/api/audit";

function makeLog(overrides: Partial<AuditLogItem> = {}): AuditLogItem {
  return {
    id: 100,
    actor_user_id: 1,
    actor_email: "admin@denvia.local",
    action: "user.permission_edit",
    target_type: "user",
    target_id: 42,
    target_email: "target@example.com",
    diff_json: {
      before: { daily_quota_override: null, subscription_status: "free" },
      after: { daily_quota_override: 50, subscription_status: "pro" },
      metadata: { pro_granted_by_admin: true },
    },
    ip: "127.0.0.1",
    ua: "Mozilla/5.0",
    trace_id: "abc-trace",
    created_at: "2026-05-01T12:00:00+09:00",
    ...overrides,
  };
}

describe("AuditDiffDrawer", () => {
  it("does not render when open=false", () => {
    const { container } = render(
      <AuditDiffDrawer open={false} log={makeLog()} onClose={() => {}} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders action label + target email + diff fields with Korean labels", () => {
    render(<AuditDiffDrawer open log={makeLog()} onClose={() => {}} />);
    expect(screen.getByText("권한 수정")).toBeTruthy();
    expect(screen.getByText(/target@example.com/)).toBeTruthy();
    expect(screen.getByText("1일 한도")).toBeTruthy();
    expect(screen.getByText("구독 상태")).toBeTruthy();
  });

  it("renders changed status with before strikethrough and after value", () => {
    render(<AuditDiffDrawer open log={makeLog()} onClose={() => {}} />);
    const subscriptionRow = screen.getByTestId("diff-row-subscription_status");
    expect(subscriptionRow.textContent).toContain("무료");
    expect(subscriptionRow.textContent).toContain("Pro");
  });

  it("renders metadata section when metadata present", () => {
    render(<AuditDiffDrawer open log={makeLog()} onClose={() => {}} />);
    expect(screen.getByText("추가 정보")).toBeTruthy();
    expect(screen.getByText("관리자 부여 Pro")).toBeTruthy();
  });

  it("calls onClose on ESC", () => {
    const onClose = vi.fn();
    render(<AuditDiffDrawer open log={makeLog()} onClose={onClose} />);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });

  it("renders system label for auto-expired action", () => {
    const log = makeLog({
      action: "user.block_auto_expired",
      diff_json: {
        before: { subscription_status: "blocked" },
        after: { subscription_status: "free" },
      },
    });
    render(<AuditDiffDrawer open log={log} onClose={() => {}} />);
    expect(screen.getByText("차단 자동 만료")).toBeTruthy();
    expect(screen.getByText(/시스템 자동/)).toBeTruthy();
  });
});
