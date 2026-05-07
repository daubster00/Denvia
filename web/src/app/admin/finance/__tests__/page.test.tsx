import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import FinanceHubPage from "../page";

describe("FinanceHubPage (Story 5.5)", () => {
  it("결제 기록 + 매출 대시보드 활성 카드 노출", () => {
    render(<FinanceHubPage />);
    expect(screen.getByText("결제 기록")).toBeTruthy();
    expect(screen.getByText("매출 대시보드")).toBeTruthy();
  });

  it("매출 대시보드 카드 상세 링크 = /admin/finance/revenue", () => {
    render(<FinanceHubPage />);
    const link = screen.getByRole("link", {
      name: /매출 대시보드 상세 페이지로 이동/,
    });
    expect(link.getAttribute("href")).toBe("/admin/finance/revenue");
  });

  it("ComingSoon 카드 2개 (예산 경고 + 고객문의)", () => {
    render(<FinanceHubPage />);
    expect(screen.getAllByText("준비 중")).toHaveLength(2);
  });
});
