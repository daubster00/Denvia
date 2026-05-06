import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SessionBootstrap } from "../SessionBootstrap";
import { useSessionStore } from "@/stores/session-store";

// next/navigation useRouter 모킹
const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

// vi.mock은 최상위에서만 호이스팅 처리 가능
vi.mock("@/features/auth/api", () => ({
  fetchMe: vi.fn(),
}));

// sessionStorage 모킹
const mockStorage: Record<string, string> = {};
Object.defineProperty(window, "sessionStorage", {
  value: {
    getItem: (k: string) => mockStorage[k] ?? null,
    setItem: (k: string, v: string) => { mockStorage[k] = v; },
    removeItem: (k: string) => { delete mockStorage[k]; },
    clear: () => { Object.keys(mockStorage).forEach(k => delete mockStorage[k]); },
  },
  writable: true,
});

const mockUser = {
  user_id: 42,
  email: "doc@denvia.com",
  role: "user" as const,
  subscription_status: "pro" as const,
  segment: "doctor" as const,
  years_of_experience: 10,
  must_reset_password: false,
  is_social: false,
};

const blockedUser = {
  ...mockUser,
  user_id: 99,
  subscription_status: "blocked" as const,
};

const mustResetUser = {
  ...mockUser,
  user_id: 77,
  must_reset_password: true,
  is_social: false,
};

function createClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

beforeEach(async () => {
  useSessionStore.setState({ user: null, isPopupOpen: false });
  Object.keys(mockStorage).forEach(k => delete mockStorage[k]);
  vi.resetAllMocks();
});

describe("SessionBootstrap", () => {
  it("GET /api/v1/me 200 → setUser가 호출된다", async () => {
    const { fetchMe } = await import("@/features/auth/api");
    vi.mocked(fetchMe).mockResolvedValue(mockUser);

    const client = createClient();
    render(
      <QueryClientProvider client={client}>
        <SessionBootstrap><div /></SessionBootstrap>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(useSessionStore.getState().user?.user_id).toBe(42);
    });
  });

  it("GET /api/v1/me 실패(401) → clearSession, 팝업 자동 오픈 안 됨", async () => {
    const { fetchMe } = await import("@/features/auth/api");
    vi.mocked(fetchMe).mockRejectedValue(new Error("401 Unauthorized"));

    const client = createClient();
    render(
      <QueryClientProvider client={client}>
        <SessionBootstrap><div /></SessionBootstrap>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(useSessionStore.getState().user).toBeNull();
    });
    // 비로그인 랜딩 정상 경로 — 팝업 자동 오픈 금지
    expect(useSessionStore.getState().isPopupOpen).toBe(false);
  });

  it("subscription_status='blocked' → /blocked로 리다이렉트", async () => {
    const { fetchMe } = await import("@/features/auth/api");
    vi.mocked(fetchMe).mockResolvedValue(blockedUser);

    const client = createClient();
    render(
      <QueryClientProvider client={client}>
        <SessionBootstrap><div /></SessionBootstrap>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith("/blocked");
    });
  });

  it("subscription_status='free' → 리다이렉트 없음", async () => {
    const { fetchMe } = await import("@/features/auth/api");
    vi.mocked(fetchMe).mockResolvedValue(mockUser);

    const client = createClient();
    render(
      <QueryClientProvider client={client}>
        <SessionBootstrap><div /></SessionBootstrap>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(useSessionStore.getState().user?.user_id).toBe(42);
    });
    expect(mockPush).not.toHaveBeenCalled();
  });

  it("must_reset_password=true → /reset-password로 리다이렉트", async () => {
    const { fetchMe } = await import("@/features/auth/api");
    vi.mocked(fetchMe).mockResolvedValue(mustResetUser);

    // 현재 경로를 "/" 시뮬레이션 (window.location.pathname = "/")
    Object.defineProperty(window, "location", {
      value: { pathname: "/" },
      writable: true,
      configurable: true,
    });

    const client = createClient();
    render(
      <QueryClientProvider client={client}>
        <SessionBootstrap><div /></SessionBootstrap>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith("/reset-password");
    });
  });

  it("must_reset_password=true이고 /reset-password 경로 → 리다이렉트 루프 없음", async () => {
    const { fetchMe } = await import("@/features/auth/api");
    vi.mocked(fetchMe).mockResolvedValue(mustResetUser);

    // 이미 /reset-password에 있는 상황 시뮬레이션
    Object.defineProperty(window, "location", {
      value: { pathname: "/reset-password" },
      writable: true,
      configurable: true,
    });

    const client = createClient();
    render(
      <QueryClientProvider client={client}>
        <SessionBootstrap><div /></SessionBootstrap>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(useSessionStore.getState().user?.user_id).toBe(77);
    });
    // /reset-password에서는 push가 호출되지 않아야 함
    expect(mockPush).not.toHaveBeenCalled();
  });
});
