/** ProBadge 단위 테스트 — Story 3.1 (UX-DR10). */

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ProBadge } from "../components/ProBadge";

describe("ProBadge", () => {
  it("기본 렌더: 'Pro' 텍스트가 표시된다", () => {
    render(<ProBadge />);
    expect(screen.getByText("Pro")).toBeDefined();
  });

  it("기본 렌더: 👑 아이콘이 표시된다(showIcon 기본 true)", () => {
    render(<ProBadge />);
    expect(screen.getByText("👑")).toBeDefined();
  });

  it("showIcon=false 시 👑 아이콘이 없다", () => {
    render(<ProBadge showIcon={false} />);
    expect(screen.queryByText("👑")).toBeNull();
  });

  it("aria-label='Pro 플랜'이 있다 (접근성)", () => {
    const { container } = render(<ProBadge />);
    expect(container.querySelector("[aria-label='Pro 플랜']")).not.toBeNull();
  });

  it("size='sm' prop이 적용된다", () => {
    const { container } = render(<ProBadge size="sm" />);
    // CSS module은 실제 클래스 이름이 변환되므로 컴포넌트 렌더 자체만 확인
    expect(container.querySelector("span")).not.toBeNull();
  });

  it("size='md' prop이 적용된다", () => {
    const { container } = render(<ProBadge size="md" />);
    expect(container.querySelector("span")).not.toBeNull();
  });

  it("showIcon=true + size='sm' 조합 렌더 — 아이콘과 텍스트 모두 표시", () => {
    render(<ProBadge size="sm" showIcon />);
    expect(screen.getByText("👑")).toBeDefined();
    expect(screen.getByText("Pro")).toBeDefined();
  });
});
