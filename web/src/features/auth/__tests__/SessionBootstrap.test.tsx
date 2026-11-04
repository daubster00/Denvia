import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SessionBootstrap } from "../SessionBootstrap";
import { useSessionStore } from "@/stores/session-store";

// next/navigation 모킹 — useRouter / usePathname / useSearchParams 모두 필요.
const mockPush = vi.fn();
const mockReplace = vi.fn();
const mockSearchParams = new URLSearchParams();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush, replace: mockReplace }),
  usePathname: () => "/",
  useSearchParams: () => mockSearchParams,
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

// ──────────────────────────────────────────────────────────────────────────────
// 2026-11-03 검수 P0-4 — 세션이 바뀌거나 끝나면 QA 대화가 남으면 안 된다.
//
// QA 대화는 sessionStorage 에 저장된다. 같은 탭에서 계정이 바뀌었는데 대화가 남으면
// 다음 사용자의 질문에 이전 사용자의 대화가 맥락으로 따라붙는다.
// ──────────────────────────────────────────────────────────────────────────────

describe("SessionBootstrap — QA 대화 소유권 (검수 P0-4)", () => {

  const turn = (id: string) => ({
    id,
    role: "user" as const,
    content: "이전 사용자의 질문",
    status: "complete" as const,
    timestamp: "2026-01-01T00:00:00.000Z",
  });

  function renderBootstrap() {
    const client = createClient();
    return render(
      <QueryClientProvider client={client}>
        <SessionBootstrap><div /></SessionBootstrap>
      </QueryClientProvider>
    );
  }

  it("다른 계정으로 로그인하면 이전 사용자의 QA 대화를 비운다", async () => {
    const { useQAStore } = await import("@/stores/qa-store");
    const { fetchMe } = await import("@/features/auth/api");
    vi.mocked(fetchMe).mockResolvedValue(mockUser); // user_id 42

    useQAStore.setState({
      messages: [turn("1")],
      pendingHomeQuestion: "이전 사용자의 대기 질문",
      ownerUserId: 10, // 앞서 다른 사용자가 쓰던 탭
    });

    renderBootstrap();

    await waitFor(() => {
      expect(useQAStore.getState().ownerUserId).toBe(42);
    });
    expect(useQAStore.getState().messages).toEqual([]);
    expect(useQAStore.getState().pendingHomeQuestion).toBeNull();
  });

  it("같은 계정이면 새로고침에도 대화를 유지한다", async () => {
    const { useQAStore } = await import("@/stores/qa-store");
    const { fetchMe } = await import("@/features/auth/api");
    vi.mocked(fetchMe).mockResolvedValue(mockUser); // user_id 42

    useQAStore.setState({ messages: [turn("1")], ownerUserId: 42 });

    renderBootstrap();

    await waitFor(() => {
      expect(useSessionStore.getState().user?.user_id).toBe(42);
    });
    expect(useQAStore.getState().messages).toHaveLength(1);
  });

  it.each([
    "AUTH_SESSION_EXPIRED",
    "AUTH_SESSION_SUPERSEDED",
    "AUTH_NOT_AUTHENTICATED",
  ])("인증 실패(%s)면 QA 대화를 비운다", async (code) => {
    const { useQAStore } = await import("@/stores/qa-store");
    const { fetchMe } = await import("@/features/auth/api");
    const { ApiError } = await import("@/types/api");
    vi.mocked(fetchMe).mockRejectedValue(
      new ApiError({ code, message: "세션이 만료되었습니다.", trace_id: "t" }),
    );

    useQAStore.setState({
      messages: [turn("1")],
      pendingHomeQuestion: "대기 질문",
      ownerUserId: 10,
    });

    renderBootstrap();

    // 401 은 react-query 가 1회 재시도하므로 넉넉히 기다린다.
    await waitFor(
      () => {
        expect(useQAStore.getState().messages).toEqual([]);
      },
      { timeout: 5000 },
    );
    expect(useQAStore.getState().ownerUserId).toBeNull();
    expect(useQAStore.getState().pendingHomeQuestion).toBeNull();
  });

  // ───────────────────────────────────────────────────────────────────────────
  // 일시 장애에서는 대화를 **보존한다** — 3차 검수 P1-1
  //
  // `/api/v1/me` 실패는 인증 만료만이 아니다. 500·502·네트워크 단절도 같은 "실패" 로
  // 들어오고, 이 컴포넌트는 **경로가 바뀔 때마다** 그 쿼리를 다시 던진다. 전부 세션
  // 종료로 취급하면 배포 중 20초간의 502 만으로 진행 중인 대화가 통째로 사라졌다
  // (sessionStorage 를 지우므로 서버가 복구돼도 돌아오지 않는다).
  // ───────────────────────────────────────────────────────────────────────────

  it.each([
    ["500 서버 오류", "INTERNAL_ERROR"],
    ["502 게이트웨이", "UNKNOWN_ERROR"],
  ])("%s 에서는 QA 대화를 보존한다", async (_label, code) => {
    const { useQAStore } = await import("@/stores/qa-store");
    const { fetchMe } = await import("@/features/auth/api");
    const { ApiError } = await import("@/types/api");
    vi.mocked(fetchMe).mockRejectedValue(
      new ApiError({ code, message: "서버 오류", trace_id: "t" }),
    );

    useQAStore.setState({
      messages: [turn("1")],
      pendingHomeQuestion: "대기 질문",
      ownerUserId: 10,
    });

    renderBootstrap();

    // 로그인 상태는 비워진다(서버 응답을 못 받았으므로).
    await waitFor(
      () => {
        expect(useSessionStore.getState().user).toBeNull();
      },
      { timeout: 5000 },
    );
    // 대화는 그대로 — 서버가 복구되면 이어서 질문할 수 있어야 한다.
    expect(useQAStore.getState().messages).toHaveLength(1);
    expect(useQAStore.getState().ownerUserId).toBe(10);
    expect(useQAStore.getState().pendingHomeQuestion).toBe("대기 질문");
  });

  it("네트워크 단절(ApiError 아님)에서도 QA 대화를 보존한다", async () => {
    const { useQAStore } = await import("@/stores/qa-store");
    const { fetchMe } = await import("@/features/auth/api");
    vi.mocked(fetchMe).mockRejectedValue(new TypeError("Failed to fetch"));

    useQAStore.setState({ messages: [turn("1")], ownerUserId: 10 });

    renderBootstrap();

    await waitFor(
      () => {
        expect(useSessionStore.getState().user).toBeNull();
      },
      { timeout: 5000 },
    );
    expect(useQAStore.getState().messages).toHaveLength(1);
    expect(useQAStore.getState().ownerUserId).toBe(10);
  });
});
