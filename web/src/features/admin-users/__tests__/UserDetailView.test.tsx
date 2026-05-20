import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type {
  UserDetailResponse,
  UserSearchItem,
} from "@/features/admin-users/api/users";
import { UserDetailView } from "../components/UserDetailView";

function withQuery(ui: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={client}>{ui}</QueryClientProvider>;
}

function makeUser(overrides: Partial<UserSearchItem> = {}): UserSearchItem {
  return {
    user_id: 1,
    email: "user@example.com",
    phone: "01012345678",
    segment: "doctor",
    years_of_experience: 5,
    subscription_status: "pro",
    is_blocked: false,
    block_until: null,
    daily_quota_override: null,
    created_at: "2026-04-01T00:00:00+09:00",
    last_login_at: null,
    withdrawn_at: null,
    pro_since: null,
    card_last4: "1234",
    card_company: "신한",
    ...overrides,
  };
}

function makeDetail(
  overrides: Partial<UserDetailResponse> = {},
): UserDetailResponse {
  return {
    user: makeUser(),
    subscription_summary: {
      current_status: "pro",
      billing_key_active: true,
      card_last4: "1234",
      card_company: "신한",
      subscription_started_at: null,
      next_charge_at: null,
    },
    recent_qa: [],
    recent_anomaly_events: [],
    ...overrides,
  };
}

describe("UserDetailView", () => {
  it("renders 4 sections (basic / subscription / qa / anomaly)", () => {
    render(
      withQuery(
        <UserDetailView
          detail={makeDetail()}
          isLoading={false}
          isError={false}
          onRetry={vi.fn()}
        />,
      ),
    );
    expect(screen.getByText("기본 정보")).toBeTruthy();
    expect(screen.getByText("결제 정보")).toBeTruthy();
    expect(screen.getByRole("heading", { name: /최근 질의/ })).toBeTruthy();
    expect(screen.getByRole("heading", { name: /최근 이상 이벤트/ })).toBeTruthy();
  });

  it("hides subscription section for withdrawn user", () => {
    const detail = makeDetail({
      user: makeUser({
        withdrawn_at: "2026-03-01T00:00:00+09:00",
        phone: null,
      }),
      subscription_summary: {
        current_status: "free",
        billing_key_active: false,
        card_last4: null,
        card_company: null,
        subscription_started_at: null,
        next_charge_at: null,
      },
    });
    render(
      withQuery(
        <UserDetailView
          detail={detail}
          isLoading={false}
          isError={false}
          onRetry={vi.fn()}
        />,
      ),
    );
    expect(screen.queryByText("결제 정보")).toBeNull();
    expect(screen.getByText("탈퇴")).toBeTruthy();
  });

  it("opens permission dialog when 권한 수정 button is clicked", () => {
    render(
      withQuery(
        <UserDetailView
          detail={makeDetail()}
          isLoading={false}
          isError={false}
          onRetry={vi.fn()}
        />,
      ),
    );
    const btn = screen.getByTestId("open-permission-dialog");
    expect(btn.hasAttribute("disabled")).toBe(false);
    fireEvent.click(btn);
    expect(screen.getByTestId("user-permission-dialog")).toBeTruthy();
  });

  it("disables 권한 수정 for withdrawn user", () => {
    const detail = makeDetail({
      user: makeUser({ withdrawn_at: "2026-03-01T00:00:00+09:00" }),
    });
    render(
      withQuery(
        <UserDetailView
          detail={detail}
          isLoading={false}
          isError={false}
          onRetry={vi.fn()}
        />,
      ),
    );
    const btn = screen.getByTestId("open-permission-dialog");
    expect(btn.hasAttribute("disabled")).toBe(true);
  });

  it("shows loading state when isLoading=true", () => {
    render(
      withQuery(
        <UserDetailView
          detail={undefined}
          isLoading
          isError={false}
          onRetry={vi.fn()}
        />,
      ),
    );
    expect(screen.getByRole("status")).toBeTruthy();
  });

  it("shows error state with retry button when isError=true", () => {
    const onRetry = vi.fn();
    render(
      withQuery(
        <UserDetailView
          detail={undefined}
          isLoading={false}
          isError
          onRetry={onRetry}
        />,
      ),
    );
    expect(screen.getByRole("alert")).toBeTruthy();
    fireEvent.click(screen.getByText("다시 시도"));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("renders 이상 이벤트 section above 최근 질의 section", () => {
    render(
      withQuery(
        <UserDetailView
          detail={makeDetail()}
          isLoading={false}
          isError={false}
          onRetry={vi.fn()}
        />,
      ),
    );
    const anomalyHeading = screen.getByRole("heading", {
      name: /최근 이상 이벤트/,
    });
    const qaHeading = screen.getByRole("heading", { name: /최근 질의/ });
    const order = anomalyHeading.compareDocumentPosition(qaHeading);
    // DOCUMENT_POSITION_FOLLOWING (4) — qaHeading comes after anomalyHeading
    expect(order & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("renders 로그 기록 link instead of 이력 보기", () => {
    render(
      withQuery(
        <UserDetailView
          detail={makeDetail()}
          isLoading={false}
          isError={false}
          onRetry={vi.fn()}
        />,
      ),
    );
    expect(screen.getByText("로그 기록")).toBeTruthy();
    expect(screen.queryByText("이력 보기")).toBeNull();
  });

  it("로그 기록 link points to /admin/users/{id}/logs", () => {
    render(
      withQuery(
        <UserDetailView
          detail={makeDetail()}
          isLoading={false}
          isError={false}
          onRetry={vi.fn()}
        />,
      ),
    );
    const link = screen.getByText("로그 기록") as HTMLAnchorElement;
    expect(link.getAttribute("href")).toBe("/admin/users/1/logs");
  });
});
