/** /my 페이지 인증 가드 단위 테스트 — Story 4.3.
 *
 * SessionBootstrap 비동기 복원 race로 store.user==null인 시점에
 * 즉시 redirect되는 회귀를 막는다.
 */

import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { useSessionStore } from "@/stores/session-store";

const mockReplace = vi.fn();
const mockPush = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mockReplace, push: mockPush }),
  usePathname: () => "/my",
}));

vi.mock("@/components/layout/TopNav", () => ({
  TopNav: () => <header data-testid="topnav-stub" />,
}));

vi.mock("@/features/account/components/AccountSummary", () => ({
  AccountSummary: () => <div data-testid="account-summary" />,
}));

vi.mock("@/features/billing/components/PaymentHistoryTable", () => ({
  PaymentHistoryTable: () => <div data-testid="payment-history" />,
}));

vi.mock("@/features/auth/api", () => ({
  fetchMe: vi.fn(),
}));

vi.mock("@/features/account/api", () => ({
  fetchUsageSummary: vi.fn(),
}));

const { fetchMe } = await import("@/features/auth/api");
const { fetchUsageSummary } = await import("@/features/account/api");

import MyPage from "../page";

function makeWrapper() {
  return function wrapper({ children }: { children: ReactNode }) {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

beforeEach(() => {
  useSessionStore.setState({ user: null });
  mockReplace.mockReset();
  mockPush.mockReset();
  vi.mocked(fetchMe).mockReset();
  vi.mocked(fetchMe).mockImplementation(() => new Promise(() => {}));
  vi.mocked(fetchUsageSummary).mockReset();
  vi.mocked(fetchUsageSummary).mockImplementation(() => new Promise(() => {}));
});

describe("MyPage — 인증 가드", () => {
  it("user=null + session query pending → 본문 미렌더 + redirect/openPopup 호출 안 함", () => {
    useSessionStore.setState({ user: null });
    vi.mocked(fetchMe).mockImplementation(() => new Promise(() => {}));
    const openPopup = vi.fn();
    useSessionStore.setState({ openPopup });

    const { container } = render(<MyPage />, { wrapper: makeWrapper() });

    expect(container.textContent).toBe("");
    expect(mockReplace).not.toHaveBeenCalled();
    expect(openPopup).not.toHaveBeenCalled();
  });

  it("user=null + session query 성공(store sync race) → redirect 안 함", async () => {
    useSessionStore.setState({ user: null });
    vi.mocked(fetchMe).mockResolvedValue({
      user_id: 1,
      email: "u@e.com",
      role: "user",
      subscription_status: "free",
      segment: null,
      years_of_experience: null,
      must_reset_password: false,
      is_social: false,
    } as never);
    const openPopup = vi.fn();
    useSessionStore.setState({ openPopup });

    render(<MyPage />, { wrapper: makeWrapper() });

    await waitFor(() => expect(vi.mocked(fetchMe)).toHaveBeenCalled());
    expect(mockReplace).not.toHaveBeenCalled();
    expect(openPopup).not.toHaveBeenCalled();
  });

  it("user=null + session query 실패 → openPopup + replace 호출", async () => {
    useSessionStore.setState({ user: null });
    vi.mocked(fetchMe).mockRejectedValue(new Error("401"));
    const openPopup = vi.fn();
    useSessionStore.setState({ openPopup });

    render(<MyPage />, { wrapper: makeWrapper() });

    // 페이지 useQuery는 retry: 1이라 isError 확정까지 ~1s + delay. waitFor timeout 확장.
    await waitFor(() => expect(openPopup).toHaveBeenCalledWith("email"), {
      timeout: 5000,
    });
    expect(mockReplace).toHaveBeenCalledWith("/?login=required");
  });

  it("로그인 시 본문 렌더 (AccountSummary + PaymentHistoryTable)", async () => {
    useSessionStore.setState({
      user: {
        user_id: 1,
        email: "u@e.com",
        role: "user",
        subscription_status: "free",
        segment: null,
        years_of_experience: null,
        must_reset_password: false,
        is_social: false,
      },
    });
    vi.mocked(fetchMe).mockResolvedValue({
      user_id: 1,
      email: "u@e.com",
      role: "user",
      subscription_status: "free",
      segment: null,
      years_of_experience: null,
      must_reset_password: false,
      is_social: false,
    } as never);

    const { findByTestId } = render(<MyPage />, { wrapper: makeWrapper() });

    expect(await findByTestId("account-summary")).toBeDefined();
    expect(await findByTestId("payment-history")).toBeDefined();
  });

  it("free + show_subscribe_button=false → 결제 내역 섹션 미렌더 (A-303 OFF)", async () => {
    useSessionStore.setState({
      user: {
        user_id: 1,
        email: "u@e.com",
        role: "user",
        subscription_status: "free",
        segment: "doctor",
        years_of_experience: 3,
        must_reset_password: false,
        is_social: false,
      },
    });
    vi.mocked(fetchMe).mockResolvedValue({
      user_id: 1,
      email: "u@e.com",
      role: "user",
      subscription_status: "free",
      segment: "doctor",
      years_of_experience: 3,
      must_reset_password: false,
      is_social: false,
    } as never);
    vi.mocked(fetchUsageSummary).mockResolvedValue({
      month_question_count: 0,
      daily_used: 0,
      daily_limit: 10,
      daily_remaining: 10,
      daily_reset_at: "2026-05-12T00:00:00+09:00",
      subscription_status: "free",
      segment: "doctor",
      years_of_experience: 3,
      show_subscribe_button: false,
    });

    const { findByTestId, queryByTestId } = render(<MyPage />, {
      wrapper: makeWrapper(),
    });

    expect(await findByTestId("account-summary")).toBeDefined();
    await waitFor(() => {
      expect(queryByTestId("payment-history")).toBeNull();
    });
  });

  it("free + show_subscribe_button=true → 결제 내역 섹션 노출 (A-303 ON)", async () => {
    useSessionStore.setState({
      user: {
        user_id: 1,
        email: "u@e.com",
        role: "user",
        subscription_status: "free",
        segment: "doctor",
        years_of_experience: 3,
        must_reset_password: false,
        is_social: false,
      },
    });
    vi.mocked(fetchMe).mockResolvedValue({
      user_id: 1,
      email: "u@e.com",
      role: "user",
      subscription_status: "free",
      segment: "doctor",
      years_of_experience: 3,
      must_reset_password: false,
      is_social: false,
    } as never);
    vi.mocked(fetchUsageSummary).mockResolvedValue({
      month_question_count: 0,
      daily_used: 0,
      daily_limit: 10,
      daily_remaining: 10,
      daily_reset_at: "2026-05-12T00:00:00+09:00",
      subscription_status: "free",
      segment: "doctor",
      years_of_experience: 3,
      show_subscribe_button: true,
    });

    const { findByTestId } = render(<MyPage />, { wrapper: makeWrapper() });

    expect(await findByTestId("account-summary")).toBeDefined();
    expect(await findByTestId("payment-history")).toBeDefined();
  });

  it("pro + show_subscribe_button=false → 결제 내역 섹션 노출 (해지/환불 진입)", async () => {
    useSessionStore.setState({
      user: {
        user_id: 1,
        email: "u@e.com",
        role: "user",
        subscription_status: "pro",
        segment: "doctor",
        years_of_experience: 5,
        must_reset_password: false,
        is_social: false,
      },
    });
    vi.mocked(fetchMe).mockResolvedValue({
      user_id: 1,
      email: "u@e.com",
      role: "user",
      subscription_status: "pro",
      segment: "doctor",
      years_of_experience: 5,
      must_reset_password: false,
      is_social: false,
    } as never);
    vi.mocked(fetchUsageSummary).mockResolvedValue({
      month_question_count: 100,
      daily_used: 0,
      daily_limit: 0,
      daily_remaining: 0,
      daily_reset_at: "2026-05-12T00:00:00+09:00",
      subscription_status: "pro",
      segment: "doctor",
      years_of_experience: 5,
      show_subscribe_button: false,
    });

    const { findByTestId } = render(<MyPage />, { wrapper: makeWrapper() });

    expect(await findByTestId("account-summary")).toBeDefined();
    expect(await findByTestId("payment-history")).toBeDefined();
  });
});
