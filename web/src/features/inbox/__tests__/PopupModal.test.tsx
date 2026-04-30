/** PopupModal 단위 테스트 — Story 4.5 (X 클릭 → POST /seen). */

import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { PopupModal } from "../components/PopupModal";

vi.mock("../api", () => ({
  markPopupSeen: vi.fn(() => Promise.resolve()),
}));

const { markPopupSeen } = await import("../api");

function makeWrapper() {
  return function wrapper({ children }: { children: ReactNode }) {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

beforeEach(() => {
  vi.mocked(markPopupSeen).mockReset();
  vi.mocked(markPopupSeen).mockResolvedValue();
});

describe("PopupModal", () => {
  it("닫기 버튼 클릭 시 markPopupSeen(popup_id) 호출", async () => {
    render(
      <PopupModal
        popup={{
          popup_id: 12,
          title: "신규 안내",
          body_html_safe: "<p>본문</p>",
          link_url: null,
          display_end: "2026-12-31T00:00:00+00:00",
        }}
      />,
      { wrapper: makeWrapper() },
    );
    fireEvent.click(screen.getByLabelText("닫기"));
    await waitFor(() =>
      expect(markPopupSeen).toHaveBeenCalledWith(12),
    );
  });

  it("link_url이 있으면 '자세히 보기' 링크 표시 + target=_blank rel=noopener", () => {
    render(
      <PopupModal
        popup={{
          popup_id: 1,
          title: "T",
          body_html_safe: "<p>x</p>",
          link_url: "https://denvia.kr/announce",
          display_end: "2026-12-31T00:00:00+00:00",
        }}
      />,
      { wrapper: makeWrapper() },
    );
    const link = screen.getByText(/자세히 보기/) as HTMLAnchorElement;
    expect(link.tagName).toBe("A");
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toContain("noopener");
    expect(link.getAttribute("rel")).toContain("noreferrer");
  });

  it("link_url이 null이면 '자세히 보기' 링크 미렌더", () => {
    render(
      <PopupModal
        popup={{
          popup_id: 1,
          title: "T",
          body_html_safe: "<p>x</p>",
          link_url: null,
          display_end: "2026-12-31T00:00:00+00:00",
        }}
      />,
      { wrapper: makeWrapper() },
    );
    expect(screen.queryByText(/자세히 보기/)).toBeNull();
  });

  it.each([
    "javascript:alert(1)",
    "JavaScript:alert(1)",
    "  javascript:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "mailto:user@evil.example",
    "vbscript:msgbox(1)",
    "file:///etc/passwd",
    "//evil.example/x",
    "/relative/path",
  ])("unsafe link_url(%s)이면 '자세히 보기' 링크 미렌더", (unsafeLink) => {
    render(
      <PopupModal
        popup={{
          popup_id: 1,
          title: "T",
          body_html_safe: "<p>x</p>",
          link_url: unsafeLink,
          display_end: "2026-12-31T00:00:00+00:00",
        }}
      />,
      { wrapper: makeWrapper() },
    );
    expect(screen.queryByText(/자세히 보기/)).toBeNull();
  });
});
