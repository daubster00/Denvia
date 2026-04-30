import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { PlanCard } from "../PlanCard";

describe("PlanCard — Story 4.3 AC-2 / AC-4", () => {
  it("free + show_subscribe_button=true → '구독하기' 링크 노출", () => {
    render(<PlanCard subscriptionStatus="free" showSubscribeButton={true} />);
    expect(screen.getByText("Basic")).toBeDefined();
    const link = screen.getByRole("link", { name: "구독하기" });
    expect(link).toBeDefined();
    expect(link.getAttribute("href")).toBe("/subscribe");
  });

  it("free + show_subscribe_button=false → 구독하기 버튼 DOM 미마운트 (FR48)", () => {
    render(<PlanCard subscriptionStatus="free" showSubscribeButton={false} />);
    expect(screen.getByText("Basic")).toBeDefined();
    expect(screen.queryByRole("link", { name: "구독하기" })).toBeNull();
  });

  it("pro → 'Pro — 무제한' + ProBadge 노출, 구독하기 버튼 미노출", () => {
    render(<PlanCard subscriptionStatus="pro" showSubscribeButton={false} />);
    expect(screen.getByText("Pro — 무제한")).toBeDefined();
    expect(screen.getByLabelText("Pro 플랜")).toBeDefined();
    expect(screen.queryByRole("link", { name: "구독하기" })).toBeNull();
  });

  it("admin → '관리자(무제한)' + 구독하기 버튼 미노출", () => {
    render(<PlanCard subscriptionStatus="admin" showSubscribeButton={false} />);
    expect(screen.getByText("관리자(무제한)")).toBeDefined();
    expect(screen.queryByRole("link", { name: "구독하기" })).toBeNull();
  });

  it("내부 500회 상한 노출 0건 (NFR-O5)", () => {
    render(<PlanCard subscriptionStatus="pro" showSubscribeButton={false} />);
    expect(screen.queryByText(/500/)).toBeNull();
  });
});
