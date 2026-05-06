/** useBillingActivation 단위 테스트 — Story 3.2. */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";

const mockIssueBillingKey = vi.fn();
const mockStartSubscription = vi.fn();
const mockSetUser = vi.fn();
let mockCurrentUser = {
  user_id: 1,
  email: "test@example.com",
  role: "user" as const,
  subscription_status: "free" as const,
  segment: null,
  years_of_experience: null,
  must_reset_password: false,
  is_social: false,
};

vi.mock("../api", () => ({
  issueBillingKey: (...args: unknown[]) => mockIssueBillingKey(...args),
  startSubscription: (...args: unknown[]) => mockStartSubscription(...args),
}));

vi.mock("@/stores/session-store", () => ({
  useSessionStore: (selector: (s: unknown) => unknown) => {
    const state = {
      user: mockCurrentUser,
      setUser: mockSetUser,
    };
    return selector(state);
  },
}));

import { useBillingActivation } from "../hooks/useBillingActivation";

describe("useBillingActivation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockCurrentUser = {
      user_id: 1,
      email: "test@example.com",
      role: "user",
      subscription_status: "free",
      segment: null,
      years_of_experience: null,
      must_reset_password: false,
      is_social: false,
    };
  });

  it("초기 status는 'idle'이다", () => {
    const { result } = renderHook(() => useBillingActivation());
    expect(result.current.status).toBe("idle");
  });

  it("activate 성공 시 issueBillingKey → startSubscription 순서 호출", async () => {
    mockIssueBillingKey.mockResolvedValue({ billing_key_id: 1 });
    mockStartSubscription.mockResolvedValue({ subscription_id: 42, amount_krw: 9900 });

    const { result } = renderHook(() => useBillingActivation());

    await act(async () => {
      await result.current.activate("auth_key", "customer_key");
    });

    expect(mockIssueBillingKey).toHaveBeenCalledWith("auth_key", "customer_key");
    expect(mockStartSubscription).toHaveBeenCalledOnce();
    expect(result.current.status).toBe("done");
  });

  it("activate 성공 시 setUser subscription_status='pro' 호출", async () => {
    mockIssueBillingKey.mockResolvedValue({ billing_key_id: 1 });
    mockStartSubscription.mockResolvedValue({ subscription_id: 42 });

    const { result } = renderHook(() => useBillingActivation());

    await act(async () => {
      await result.current.activate("auth_key", "customer_key");
    });

    expect(mockSetUser).toHaveBeenCalledWith(
      expect.objectContaining({ subscription_status: "pro" })
    );
  });

  it("activate 실패 시 status='error' + errorMessage 설정", async () => {
    mockIssueBillingKey.mockRejectedValue(new Error("카드 결제 거절"));

    const { result } = renderHook(() => useBillingActivation());

    await act(async () => {
      await result.current.activate("auth_key", "customer_key");
    });

    expect(result.current.status).toBe("error");
    expect(result.current.errorMessage).toBe("카드 결제 거절");
  });
});
