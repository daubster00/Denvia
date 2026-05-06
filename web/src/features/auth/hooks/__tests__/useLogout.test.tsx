import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useLogout } from "../useLogout";
import { useSessionStore } from "@/stores/session-store";

const mockReplace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mockReplace }),
}));

vi.mock("@/features/auth/api", () => ({
  logout: vi.fn(),
}));

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  mockReplace.mockReset();
  vi.resetAllMocks();
  useSessionStore.setState({
    user: {
      user_id: 1,
      email: "doc@denvia.com",
      role: "user",
      subscription_status: "free",
      segment: "doctor",
      years_of_experience: 5,
      must_reset_password: false,
      is_social: false,
    },
    isPopupOpen: false,
  });
});

describe("useLogout — Story 2.7 (AC-2)", () => {
  it("성공 시 clearSession + router.replace('/') 호출", async () => {
    const { logout } = await import("@/features/auth/api");
    vi.mocked(logout).mockResolvedValue(undefined);

    const { result } = renderHook(() => useLogout(), { wrapper });
    await act(async () => {
      await result.current();
    });

    expect(useSessionStore.getState().user).toBeNull();
    expect(mockReplace).toHaveBeenCalledWith("/");
  });

  it("서버 실패(5xx 등)에도 clearSession + router.replace 보장 (try/finally)", async () => {
    const { logout } = await import("@/features/auth/api");
    vi.mocked(logout).mockRejectedValue(new Error("500 Server Error"));

    const { result } = renderHook(() => useLogout(), { wrapper });
    await act(async () => {
      await result.current();
    });

    expect(useSessionStore.getState().user).toBeNull();
    expect(mockReplace).toHaveBeenCalledWith("/");
  });
});
