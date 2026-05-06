import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { UserEditHistoryTable } from "../components/UserEditHistoryTable";
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
      before: { daily_quota_override: null },
      after: { daily_quota_override: 50 },
    },
    ip: "127.0.0.1",
    ua: null,
    trace_id: "abc-trace",
    created_at: "2026-05-01T12:00:00+09:00",
    ...overrides,
  };
}

describe("UserEditHistoryTable", () => {
  it("renders rows with action label and target email", () => {
    render(
      <UserEditHistoryTable
        items={[makeLog()]}
        page={1}
        perPage={20}
        total={1}
        isLoading={false}
        isError={false}
        onPageChange={() => {}}
        onSelect={() => {}}
        onResetFilters={() => {}}
      />,
    );
    expect(screen.getByText("권한 수정")).toBeTruthy();
    expect(screen.getByText(/target@example.com/)).toBeTruthy();
  });

  it("calls onSelect when detail button clicked", () => {
    const onSelect = vi.fn();
    const log = makeLog();
    render(
      <UserEditHistoryTable
        items={[log]}
        page={1}
        perPage={20}
        total={1}
        isLoading={false}
        isError={false}
        onPageChange={() => {}}
        onSelect={onSelect}
        onResetFilters={() => {}}
      />,
    );
    fireEvent.click(screen.getByTestId("audit-detail-button-100"));
    expect(onSelect).toHaveBeenCalledWith(log);
  });

  it("renders system actor label for auto-expired action", () => {
    const log = makeLog({
      action: "user.block_auto_expired",
      diff_json: {
        before: { subscription_status: "blocked" },
        after: { subscription_status: "free" },
      },
    });
    render(
      <UserEditHistoryTable
        items={[log]}
        page={1}
        perPage={20}
        total={1}
        isLoading={false}
        isError={false}
        onPageChange={() => {}}
        onSelect={() => {}}
        onResetFilters={() => {}}
      />,
    );
    expect(screen.getByText("시스템 자동")).toBeTruthy();
  });

  it("renders empty state when items is empty", () => {
    const onReset = vi.fn();
    render(
      <UserEditHistoryTable
        items={[]}
        page={1}
        perPage={20}
        total={0}
        isLoading={false}
        isError={false}
        onPageChange={() => {}}
        onSelect={() => {}}
        onResetFilters={onReset}
      />,
    );
    expect(screen.getByText("수정 이력이 없습니다")).toBeTruthy();
    fireEvent.click(screen.getByText("필터 초기화"));
    expect(onReset).toHaveBeenCalled();
  });

  it("paginates with previous/next buttons", () => {
    const onPageChange = vi.fn();
    render(
      <UserEditHistoryTable
        items={[makeLog()]}
        page={2}
        perPage={20}
        total={50}
        isLoading={false}
        isError={false}
        onPageChange={onPageChange}
        onSelect={() => {}}
        onResetFilters={() => {}}
      />,
    );
    fireEvent.click(screen.getByText("이전"));
    expect(onPageChange).toHaveBeenCalledWith(1);
    fireEvent.click(screen.getByText("다음"));
    expect(onPageChange).toHaveBeenCalledWith(3);
  });
});
