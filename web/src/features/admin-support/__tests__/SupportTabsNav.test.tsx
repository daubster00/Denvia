import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { SupportTabsNav } from "../components/SupportTabsNav";

describe("SupportTabsNav (Story 9.3)", () => {
  it("renders inquiries + refunds tabs with counts", () => {
    render(
      <SupportTabsNav
        activeTab="inquiries"
        inquiryCount={12}
        refundCount={3}
        onChange={() => {}}
      />,
    );
    expect(screen.queryByRole("tab", { name: /문의/ })).not.toBeNull();
    expect(screen.queryByRole("tab", { name: /환불 검토/ })).not.toBeNull();
    expect(screen.queryByLabelText("12건")).not.toBeNull();
    expect(screen.queryByLabelText("3건")).not.toBeNull();
  });

  it("marks active tab with aria-selected=true", () => {
    render(
      <SupportTabsNav
        activeTab="refunds"
        inquiryCount={0}
        refundCount={0}
        onChange={() => {}}
      />,
    );
    const refundsTab = screen.getByTestId("support-tab-refunds");
    expect(refundsTab.getAttribute("aria-selected")).toBe("true");
    const inquiriesTab = screen.getByTestId("support-tab-inquiries");
    expect(inquiriesTab.getAttribute("aria-selected")).toBe("false");
  });

  it("invokes onChange with the clicked tab key", () => {
    const onChange = vi.fn();
    render(
      <SupportTabsNav
        activeTab="inquiries"
        inquiryCount={5}
        refundCount={2}
        onChange={onChange}
      />,
    );
    fireEvent.click(screen.getByTestId("support-tab-refunds"));
    expect(onChange).toHaveBeenCalledWith("refunds");
  });
});
