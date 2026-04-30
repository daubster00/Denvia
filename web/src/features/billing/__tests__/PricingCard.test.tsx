/** PricingCard 단위 테스트 — Story 3.1. */

import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { PricingCard } from "../components/PricingCard";
import type { PlanItem } from "../types";

const freePlan: PlanItem = {
  tier: "free",
  name: "Basic",
  price_krw: 0,
  period: null,
  features: ["하루 3회 Q&A", "기본 치과 지식 답변"],
  cta_label: "현재 이용 중",
  is_recommended: false,
};

const proPlan: PlanItem = {
  tier: "pro",
  name: "Pro",
  price_krw: 9900,
  period: "/ 월",
  features: ["무제한 Q&A", "심화 임상 답변", "응답 속도 우선"],
  cta_label: "Pro 시작하기",
  is_recommended: true,
};

describe("PricingCard — free tier", () => {
  it("Basic 플랜 heading이 렌더된다", () => {
    render(<PricingCard plan={freePlan} />);
    const heading = screen.getByRole("heading", { level: 2 });
    expect(heading.textContent).toBe("Basic");
  });

  it("가격 0원이 '0원' 텍스트로 price 영역에 표시된다", () => {
    const { container } = render(<PricingCard plan={freePlan} />);
    // price span이 "0원"을 포함하는지 확인
    const priceEls = container.querySelectorAll("[class*='price']");
    const hasZeroWon = Array.from(priceEls).some((el) => el.textContent === "0원");
    expect(hasZeroWon).toBe(true);
  });

  it("Basic 플랜 features가 렌더된다", () => {
    render(<PricingCard plan={freePlan} />);
    for (const feature of freePlan.features) {
      expect(screen.getByText(feature)).toBeDefined();
    }
  });

  it("Basic 플랜 CTA 버튼이 disabled 상태다", () => {
    render(<PricingCard plan={freePlan} />);
    const btn = screen.getByRole("button", { name: /현재 이용 중/ });
    expect((btn as HTMLButtonElement).disabled).toBe(true);
  });

  it("Basic 플랜에 ProBadge가 없다", () => {
    const { container } = render(<PricingCard plan={freePlan} />);
    expect(container.textContent).not.toContain("👑");
  });
});

describe("PricingCard — pro tier", () => {
  it("Pro 플랜 heading이 렌더된다", () => {
    render(<PricingCard plan={proPlan} />);
    // h2 planName에 "Pro" 텍스트 확인 (ProBadge의 span.Pro와 구분)
    const heading = screen.getByRole("heading", { level: 2 });
    expect(heading.textContent).toBe("Pro");
  });

  it("Pro 가격이 렌더된다", () => {
    render(<PricingCard plan={proPlan} />);
    expect(screen.getByText("9,900원")).toBeDefined();
  });

  it("period '/ 월'이 렌더된다", () => {
    render(<PricingCard plan={proPlan} />);
    expect(screen.getByText("/ 월")).toBeDefined();
  });

  it("Pro 플랜 features가 렌더된다", () => {
    render(<PricingCard plan={proPlan} />);
    for (const feature of proPlan.features) {
      expect(screen.getByText(feature)).toBeDefined();
    }
  });

  it("isRecommended=true여도 ProBadge는 표시되지 않는다", () => {
    const { container } = render(<PricingCard plan={proPlan} />);
    expect(container.textContent).not.toContain("👑");
  });

  it("Pro CTA 버튼이 활성 상태다", () => {
    render(<PricingCard plan={proPlan} />);
    const btn = screen.getByRole("button", { name: /Pro 시작하기/ });
    expect((btn as HTMLButtonElement).disabled).toBe(false);
  });

  it("CTA 버튼 클릭 시 onCta가 호출된다", () => {
    const onCta = vi.fn();
    render(<PricingCard plan={proPlan} onCta={onCta} />);
    const btn = screen.getByRole("button", { name: /Pro 시작하기/ });
    fireEvent.click(btn);
    expect(onCta).toHaveBeenCalledTimes(1);
  });
});
