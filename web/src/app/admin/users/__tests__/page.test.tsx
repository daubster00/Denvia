import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import AdminUsersPage from "../page";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, replace: vi.fn() }),
}));

vi.mock("@/features/admin-users/api/users", () => ({
  fetchUsers: vi.fn(),
  fetchUserDetail: vi.fn(),
}));

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...rest
  }: {
    href: string;
    children: React.ReactNode;
  }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

function renderWithQuery(ui: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("AdminUsersPage", () => {
  it("renders page header and search bar on mount", async () => {
    const { fetchUsers } = await import("@/features/admin-users/api/users");
    (fetchUsers as ReturnType<typeof vi.fn>).mockResolvedValue({
      items: [],
      page: 1,
      per_page: 20,
      total: 0,
    });
    renderWithQuery(<AdminUsersPage />);
    expect(screen.getByText("고객 관리")).toBeTruthy();
    expect(screen.getByLabelText("사용자 통합 검색")).toBeTruthy();
  });

  it("renders user rows after fetchUsers resolves", async () => {
    const { fetchUsers } = await import("@/features/admin-users/api/users");
    (fetchUsers as ReturnType<typeof vi.fn>).mockResolvedValue({
      items: [
        {
          user_id: 1,
          email: "first@example.com",
          phone: "01011112222",
          segment: "dentist",
          years_of_experience: 3,
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
        },
      ],
      page: 1,
      per_page: 20,
      total: 1,
    });
    renderWithQuery(<AdminUsersPage />);
    await waitFor(() => {
      expect(screen.getByText("first@example.com")).toBeTruthy();
    });
  });

  it("navigates to user detail page when row is clicked", async () => {
    const { fetchUsers } = await import("@/features/admin-users/api/users");
    const item = {
      user_id: 7,
      email: "drawer@example.com",
      phone: "01099998888",
      segment: "dentist" as const,
      years_of_experience: 10,
      subscription_status: "pro" as const,
      is_blocked: false,
      block_until: null,
      daily_quota_override: null,
      created_at: "2026-04-01T00:00:00+09:00",
      last_login_at: null,
      withdrawn_at: null,
      pro_since: null,
      card_last4: "4321",
      card_company: "삼성카드",
    };
    (fetchUsers as ReturnType<typeof vi.fn>).mockResolvedValue({
      items: [item],
      page: 1,
      per_page: 20,
      total: 1,
    });

    renderWithQuery(<AdminUsersPage />);
    await waitFor(() => {
      expect(screen.getByText("drawer@example.com")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("user-row-7"));

    expect(pushMock).toHaveBeenCalledWith("/admin/users/7");
  });
});
