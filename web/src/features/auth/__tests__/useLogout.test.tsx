/**
 * useLogout — 로그아웃 시 QA 대화까지 비운다. 2026-11-03 검수 P0-4.
 *
 * QA 대화는 sessionStorage 에 저장되므로, 로그아웃만으로는 같은 탭에 그대로 남았다.
 * 다음 사용자가 로그인해 질문하면 이전 사용자의 대화가 맥락으로 따라붙는다.
 * 서버 로그아웃이 실패해 **강제 로그아웃**이 되는 경우까지 비워야 한다.
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { renderHook } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

const mockReplace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: mockReplace }),
  usePathname: () => "/chat",
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/features/auth/api", () => ({
  logout: vi.fn(),
}));

import { logout } from "@/features/auth/api";
import { useLogout } from "@/features/auth/hooks/useLogout";
import { useQAStore } from "@/stores/qa-store";
import { useSessionStore } from "@/stores/session-store";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const CONVERSATION = [
  {
    id: "u1",
    role: "user" as const,
    content: "A 사용자의 질문",
    status: "complete" as const,
    timestamp: "2026-01-01T00:00:00.000Z",
  },
  {
    id: "a1",
    role: "assistant" as const,
    content: "A 사용자의 답변",
    status: "complete" as const,
    qaLogId: 101,
    timestamp: "2026-01-01T00:00:00.000Z",
  },
];

beforeEach(() => {
  vi.clearAllMocks();
  useQAStore.setState({
    messages: [...CONVERSATION],
    pendingHomeQuestion: "대기 질문",
    ownerUserId: 10,
  });
});

describe("useLogout", () => {
  it("정상 로그아웃 시 QA 대화·대기 질문·주인 정보를 모두 비운다", async () => {
    vi.mocked(logout).mockResolvedValue(undefined as never);

    const { result } = renderHook(() => useLogout(), { wrapper });
    await result.current();

    const s = useQAStore.getState();
    expect(s.messages).toEqual([]);
    expect(s.pendingHomeQuestion).toBeNull();
    expect(s.ownerUserId).toBeNull();
    expect(useSessionStore.getState().user).toBeNull();
  });

  it("서버 로그아웃이 실패해도(강제 로그아웃) QA 대화를 비운다", async () => {
    vi.mocked(logout).mockRejectedValue(new Error("500 Internal Server Error"));

    const { result } = renderHook(() => useLogout(), { wrapper });
    await result.current();

    expect(useQAStore.getState().messages).toEqual([]);
    expect(useQAStore.getState().ownerUserId).toBeNull();
    expect(mockReplace).toHaveBeenCalledWith("/");
  });
});
