import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import type {
  UserSearchItem,
  UserSearchListResponse,
} from "@/features/admin-users/api/users";
import { UserSearchTable } from "../components/UserSearchTable";

function makeItem(overrides: Partial<UserSearchItem> = {}): UserSearchItem {
  return {
    user_id: 1,
    email: "user@example.com",
    phone: "01012345678",
    segment: "dentist",
    years_of_experience: 5,
    subscription_status: "free",
    is_blocked: false,
    block_until: null,
    daily_quota_override: null,
    created_at: "2026-04-01T00:00:00+09:00",
    last_login_at: null,
    withdrawn_at: null,
    pro_since: null,
    card_last4: null,
    card_company: null,
    ...overrides,
  };
}

function makeData(items: UserSearchItem[]): UserSearchListResponse {
  return { items, page: 1, per_page: 20, total: items.length };
}

const noopProps = {
  isLoading: false,
  isError: false,
  page: 1,
  perPage: 20,
  onPageChange: vi.fn(),
  onSelectUser: vi.fn(),
  onResetFilters: vi.fn(),
  onRetry: vi.fn(),
};

describe("UserSearchTable", () => {
  it("renders all rows from data.items", () => {
    const data = makeData([
      makeItem({ user_id: 1, email: "a@a.com" }),
      makeItem({ user_id: 2, email: "b@b.com" }),
    ]);
    render(<UserSearchTable {...noopProps} data={data} />);
    expect(screen.getByText("a@a.com")).toBeTruthy();
    expect(screen.getByText("b@b.com")).toBeTruthy();
  });

  it("calls onSelectUser when row is clicked", () => {
    const onSelectUser = vi.fn();
    const item = makeItem({ user_id: 7 });
    render(
      <UserSearchTable
        {...noopProps}
        data={makeData([item])}
        onSelectUser={onSelectUser}
      />,
    );
    fireEvent.click(screen.getByTestId("user-row-7"));
    expect(onSelectUser).toHaveBeenCalledWith(item);
  });

  it("applies rowWithdrawn class for withdrawn users", () => {
    const data = makeData([
      makeItem({
        user_id: 9,
        email: "withdrawn_9_abcdef",
        phone: null,
        withdrawn_at: "2026-03-01T00:00:00+09:00",
      }),
    ]);
    render(<UserSearchTable {...noopProps} data={data} />);
    const row = screen.getByTestId("user-row-9");
    expect(row.getAttribute("data-withdrawn")).toBe("true");
    expect(screen.getByText("탈퇴")).toBeTruthy();
  });

  it("renders EmptyState when total=0 and not loading", () => {
    render(<UserSearchTable {...noopProps} data={makeData([])} />);
    expect(
      screen.getByText("검색 조건에 해당하는 사용자가 없습니다"),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: "검색 조건 초기화" })).toBeTruthy();
  });
});
