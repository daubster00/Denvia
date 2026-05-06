import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { UserPermissionDialog } from "../components/UserPermissionDialog";
import type { UserSearchItem } from "@/features/admin-users/api/users";

vi.mock("@/features/admin-users/api/users", async () => {
  const actual = await vi.importActual<
    typeof import("@/features/admin-users/api/users")
  >("@/features/admin-users/api/users");
  return {
    ...actual,
    updateUserPermission: vi.fn(),
  };
});

function withQuery(ui: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={client}>{ui}</QueryClientProvider>;
}

function makeUser(overrides: Partial<UserSearchItem> = {}): UserSearchItem {
  return {
    user_id: 12,
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

beforeEach(() => {
  vi.clearAllMocks();
});

describe("UserPermissionDialog", () => {
  it("does not render when open=false", () => {
    const { container } = render(
      withQuery(
        <UserPermissionDialog
          open={false}
          user={makeUser()}
          onClose={() => {}}
        />,
      ),
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders user info header + status radios", () => {
    render(
      withQuery(
        <UserPermissionDialog open user={makeUser()} onClose={() => {}} />,
      ),
    );
    expect(screen.getByText("user@example.com")).toBeTruthy();
    expect(screen.getByText("무료 (free)")).toBeTruthy();
    expect(screen.getByText("Pro (pro)")).toBeTruthy();
    expect(screen.getByText("차단 (blocked)")).toBeTruthy();
  });

  it("disables save until pro confirmation when switching to pro", () => {
    render(
      withQuery(
        <UserPermissionDialog open user={makeUser()} onClose={() => {}} />,
      ),
    );
    const proRadio = screen.getByLabelText("Pro (pro)");
    fireEvent.click(proRadio);
    expect(screen.getByTestId("save-button").hasAttribute("disabled")).toBe(
      true,
    );
    fireEvent.click(screen.getByTestId("pro-confirm-checkbox"));
    expect(screen.getByTestId("save-button").hasAttribute("disabled")).toBe(
      false,
    );
  });

  it("requires reason 1~200 chars when switching to blocked", () => {
    render(
      withQuery(
        <UserPermissionDialog open user={makeUser()} onClose={() => {}} />,
      ),
    );
    fireEvent.click(screen.getByLabelText("차단 (blocked)"));
    expect(screen.getByTestId("save-button").hasAttribute("disabled")).toBe(
      true,
    );
    fireEvent.change(screen.getByTestId("reason-textarea"), {
      target: { value: "광고 봇 의심" },
    });
    expect(screen.getByTestId("save-button").hasAttribute("disabled")).toBe(
      false,
    );
  });

  it("invokes ESC to close", () => {
    const onClose = vi.fn();
    render(
      withQuery(
        <UserPermissionDialog open user={makeUser()} onClose={onClose} />,
      ),
    );
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });

  it("renders unblock button only for blocked user", () => {
    const { rerender } = render(
      withQuery(
        <UserPermissionDialog open user={makeUser()} onClose={() => {}} />,
      ),
    );
    expect(screen.queryByTestId("unblock-button")).toBeNull();
    rerender(
      withQuery(
        <UserPermissionDialog
          open
          user={makeUser({ subscription_status: "blocked", is_blocked: true })}
          onClose={() => {}}
        />,
      ),
    );
    expect(screen.getByTestId("unblock-button")).toBeTruthy();
  });

  it("opens unblock confirm modal on unblock click", () => {
    render(
      withQuery(
        <UserPermissionDialog
          open
          user={makeUser({ subscription_status: "blocked", is_blocked: true })}
          onClose={() => {}}
        />,
      ),
    );
    fireEvent.click(screen.getByTestId("unblock-button"));
    expect(screen.getByTestId("unblock-confirm")).toBeTruthy();
  });

  it("submits successful save and calls onSuccess + onClose", async () => {
    const { updateUserPermission } = await import(
      "@/features/admin-users/api/users"
    );
    (updateUserPermission as ReturnType<typeof vi.fn>).mockResolvedValue({
      ...makeUser(),
      daily_quota_override: 50,
    });
    const onClose = vi.fn();
    const onSuccess = vi.fn();
    render(
      withQuery(
        <UserPermissionDialog
          open
          user={makeUser()}
          onClose={onClose}
          onSuccess={onSuccess}
        />,
      ),
    );
    // 한도 변경
    fireEvent.click(screen.getByLabelText("기본값 사용")); // toggle off
    fireEvent.change(screen.getByTestId("quota-input"), {
      target: { value: "50" },
    });
    fireEvent.click(screen.getByTestId("save-button"));
    await waitFor(() => {
      expect(onSuccess).toHaveBeenCalled();
      expect(onClose).toHaveBeenCalled();
    });
    expect(updateUserPermission).toHaveBeenCalledWith(12, {
      daily_quota_override: 50,
    });
  });

  // ── Issue 3: 이미 차단된 사용자 편집 ──────────────────────────────────────────

  it("already-blocked user: quota-only change does not require reason", () => {
    render(
      withQuery(
        <UserPermissionDialog
          open
          user={makeUser({ subscription_status: "blocked", is_blocked: true })}
          onClose={() => {}}
        />,
      ),
    );
    // 상태는 blocked 그대로, reason 미입력, quota만 변경
    fireEvent.click(screen.getByLabelText("기본값 사용")); // toggle off default
    fireEvent.change(screen.getByTestId("quota-input"), {
      target: { value: "30" },
    });
    // save 버튼이 활성화되어야 함 (reason 없어도 됨)
    expect(screen.getByTestId("save-button").hasAttribute("disabled")).toBe(false);
  });

  it("already-blocked user: quota-only payload contains no block_action", async () => {
    const { updateUserPermission } = await import(
      "@/features/admin-users/api/users"
    );
    (updateUserPermission as ReturnType<typeof vi.fn>).mockResolvedValue(
      makeUser({ subscription_status: "blocked", is_blocked: true, daily_quota_override: 30 }),
    );
    render(
      withQuery(
        <UserPermissionDialog
          open
          user={makeUser({ subscription_status: "blocked", is_blocked: true })}
          onClose={() => {}}
        />,
      ),
    );
    fireEvent.click(screen.getByLabelText("기본값 사용"));
    fireEvent.change(screen.getByTestId("quota-input"), { target: { value: "30" } });
    fireEvent.click(screen.getByTestId("save-button"));
    await waitFor(() => {
      expect(updateUserPermission).toHaveBeenCalledWith(12, {
        daily_quota_override: 30,
      });
    });
    // block_action이 없어야 함
    const [, calledPayload] = (updateUserPermission as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(calledPayload).not.toHaveProperty("block_action");
  });

  it("already-blocked user: providing reason enables block param update", async () => {
    const { updateUserPermission } = await import(
      "@/features/admin-users/api/users"
    );
    (updateUserPermission as ReturnType<typeof vi.fn>).mockResolvedValue(
      makeUser({ subscription_status: "blocked", is_blocked: true }),
    );
    render(
      withQuery(
        <UserPermissionDialog
          open
          user={makeUser({ subscription_status: "blocked", is_blocked: true })}
          onClose={() => {}}
        />,
      ),
    );
    // 기간을 7일로, 사유를 입력
    fireEvent.change(
      screen.getByRole("combobox"),
      { target: { value: "168" } },
    );
    fireEvent.change(screen.getByTestId("reason-textarea"), {
      target: { value: "재차단 사유 수정" },
    });
    expect(screen.getByTestId("save-button").hasAttribute("disabled")).toBe(false);
    fireEvent.click(screen.getByTestId("save-button"));
    await waitFor(() => {
      expect(updateUserPermission).toHaveBeenCalledWith(
        12,
        expect.objectContaining({
          block_action: { duration_hours: 168, reason: "재차단 사유 수정" },
        }),
      );
    });
    // subscription_status는 없어야 함 (block_action만 전달)
    const [, calledPayload] = (updateUserPermission as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(calledPayload).not.toHaveProperty("subscription_status");
  });

  it("renders inline error when server returns 422 BLOCK_ACTION_CONFLICT", async () => {
    const { updateUserPermission, UserPermissionUpdateError } = await import(
      "@/features/admin-users/api/users"
    );
    (updateUserPermission as ReturnType<typeof vi.fn>).mockRejectedValue(
      new UserPermissionUpdateError(
        422,
        "BLOCK_ACTION_CONFLICT",
        "차단과 차단 해제는 동시에 수행할 수 없습니다.",
        "trace-abc",
      ),
    );
    render(
      withQuery(
        <UserPermissionDialog open user={makeUser()} onClose={() => {}} />,
      ),
    );
    fireEvent.click(screen.getByLabelText("기본값 사용"));
    fireEvent.change(screen.getByTestId("quota-input"), {
      target: { value: "50" },
    });
    fireEvent.click(screen.getByTestId("save-button"));
    await waitFor(() => {
      expect(
        screen.getByText("차단과 차단 해제는 동시에 수행할 수 없습니다."),
      ).toBeTruthy();
    });
  });
});
