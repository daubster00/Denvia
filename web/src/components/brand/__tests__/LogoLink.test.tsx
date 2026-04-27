/**
 * LogoLink 컴포넌트 단위 테스트 — Story 2.5 (AC-5)
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { LogoLink } from "../LogoLink";

vi.mock("next/image", () => ({
  default: ({ alt }: { alt: string }) => <img alt={alt} />,
}));

vi.mock("next/link", () => ({
  default: ({
    children,
    href,
    "aria-label": ariaLabel,
    onClick,
    style,
  }: {
    children: React.ReactNode;
    href: string;
    "aria-label"?: string;
    onClick?: () => void;
    style?: React.CSSProperties;
  }) => (
    <a href={href} aria-label={ariaLabel} onClick={onClick} style={style}>
      {children}
    </a>
  ),
}));

describe("LogoLink", () => {
  it("onResetChat 없음 → aria-label='Denvia 홈'", () => {
    render(<LogoLink />);
    const link = screen.getByRole("link");
    expect(link.getAttribute("aria-label")).toBe("Denvia 홈");
  });

  it("onResetChat 있음 → aria-label='대화 초기화 및 홈으로'", () => {
    const onReset = vi.fn();
    render(<LogoLink onResetChat={onReset} />);
    const link = screen.getByRole("link");
    expect(link.getAttribute("aria-label")).toBe("대화 초기화 및 홈으로");
  });

  it("클릭 시 onResetChat 호출", () => {
    const onReset = vi.fn();
    render(<LogoLink onResetChat={onReset} />);
    fireEvent.click(screen.getByRole("link"));
    expect(onReset).toHaveBeenCalledTimes(1);
  });

  it("onResetChat 없을 때 클릭해도 오류 없음", () => {
    render(<LogoLink />);
    expect(() => fireEvent.click(screen.getByRole("link"))).not.toThrow();
  });
});
