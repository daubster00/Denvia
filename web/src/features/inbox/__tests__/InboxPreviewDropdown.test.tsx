/** InboxPreviewDropdown 노출 조건 테스트 — #118.
 *
 * - 안읽은 쪽지가 있으면 최신 1건만 자동 미리보기 노출
 * - 전부 읽은 계정에는 렌더 안 함
 * - X 닫기는 현재 페이지에서만 — 페이지 이동 시 재노출
 * - 읽음 처리 후(서버가 빈 배열 응답) 미리보기 소멸
 */

import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { InboxPreviewDropdown } from "../components/InboxPreviewDropdown";
import type { InboxPreviewResponse } from "../types";
import { useSessionStore } from "@/stores/session-store";

vi.mock("../api", () => ({
  fetchInboxPreview: vi.fn(),
}));

// 페이지 이동(pathname 변경) 시나리오 검증을 위해 usePathname 을 제어 가능하게 모킹.
const mockPathname = vi.fn<() => string>(() => "/");
vi.mock("next/navigation", () => ({
  usePathname: () => mockPathname(),
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

const { fetchInboxPreview } = await import("../api");

function makeWrapper() {
  return function wrapper({ children }: { children: ReactNode }) {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

const twoUnread: InboxPreviewResponse = {
  items: [
    {
      message_id: 11,
      type: "notice",
      title: "최신 안읽은 쪽지",
      is_read: false,
      created_at: new Date().toISOString(),
    },
    {
      message_id: 10,
      type: "system",
      title: "이전 안읽은 쪽지",
      is_read: false,
      created_at: new Date(Date.now() - 3_600_000).toISOString(),
    },
  ],
  max_count: 5,
};

const allRead: InboxPreviewResponse = { items: [], max_count: 5 };

function loginUser() {
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
}

beforeEach(() => {
  vi.mocked(fetchInboxPreview).mockReset();
  mockPathname.mockReturnValue("/");
  useSessionStore.setState({ user: null });
});

describe("InboxPreviewDropdown — #118 자동 미리보기", () => {
  it("안읽은 쪽지가 있으면 최신 1건만 자동 노출된다", async () => {
    loginUser();
    vi.mocked(fetchInboxPreview).mockResolvedValue(twoUnread);

    render(<InboxPreviewDropdown />, { wrapper: makeWrapper() });
    await waitFor(() =>
      expect(screen.getByText("최신 안읽은 쪽지")).toBeDefined(),
    );
    // 최신 1건만 — 두 번째 안읽은 쪽지는 미리보기에 없음.
    expect(screen.queryByText("이전 안읽은 쪽지")).toBeNull();
    expect(screen.getByRole("dialog", { name: "쪽지함 미리보기" })).toBeDefined();
  });

  it("안읽은 쪽지가 0건이면 렌더하지 않는다", async () => {
    loginUser();
    vi.mocked(fetchInboxPreview).mockResolvedValue(allRead);

    render(<InboxPreviewDropdown />, { wrapper: makeWrapper() });
    await waitFor(() => expect(fetchInboxPreview).toHaveBeenCalled());
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("X 닫기는 현재 페이지에서만 — 페이지 이동 시 다시 노출된다", async () => {
    loginUser();
    vi.mocked(fetchInboxPreview).mockResolvedValue(twoUnread);

    const { rerender } = render(<InboxPreviewDropdown />, {
      wrapper: makeWrapper(),
    });
    await waitFor(() =>
      expect(screen.getByText("최신 안읽은 쪽지")).toBeDefined(),
    );

    fireEvent.click(screen.getByRole("button", { name: "미리보기 닫기" }));
    expect(screen.queryByRole("dialog")).toBeNull();

    // 다른 페이지로 이동 → 아직 안 읽었으므로 다시 노출.
    mockPathname.mockReturnValue("/my");
    rerender(<InboxPreviewDropdown />);
    await waitFor(() =>
      expect(screen.getByText("최신 안읽은 쪽지")).toBeDefined(),
    );
  });

  it("읽음 처리 후(서버 응답 빈 배열)에는 페이지를 이동해도 노출되지 않는다", async () => {
    loginUser();
    vi.mocked(fetchInboxPreview)
      .mockResolvedValueOnce(twoUnread)
      .mockResolvedValue(allRead);

    const { rerender } = render(<InboxPreviewDropdown />, {
      wrapper: makeWrapper(),
    });
    await waitFor(() =>
      expect(screen.getByText("최신 안읽은 쪽지")).toBeDefined(),
    );

    // 페이지 이동 → useInboxPreview 가 refetch → 미읽음 0건 → 미리보기 소멸.
    mockPathname.mockReturnValue("/my");
    rerender(<InboxPreviewDropdown />);
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(fetchInboxPreview).toHaveBeenCalledTimes(2);
  });
});
