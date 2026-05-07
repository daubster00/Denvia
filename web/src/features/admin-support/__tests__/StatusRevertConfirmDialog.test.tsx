import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { StatusRevertConfirmDialog } from "../components/StatusRevertConfirmDialog";

describe("StatusRevertConfirmDialog (Story 9.3 AC-6)", () => {
  it("does not render when closed", () => {
    const { container } = render(
      <StatusRevertConfirmDialog
        open={false}
        currentStatus="resolved"
        requestedStatus="open"
        isPending={false}
        onCancel={() => {}}
        onConfirm={() => {}}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("shows the current → requested status flow when open", () => {
    render(
      <StatusRevertConfirmDialog
        open={true}
        currentStatus="resolved"
        requestedStatus="open"
        isPending={false}
        onCancel={() => {}}
        onConfirm={() => {}}
      />,
    );
    // 최소 한 번씩 등장하면 OK (라벨 자체는 여러 위치에 노출)
    expect(screen.queryAllByText(/완료/).length).toBeGreaterThan(0);
    expect(screen.queryAllByText(/신규/).length).toBeGreaterThan(0);
  });

  it("invokes onConfirm when 되돌리기 clicked", () => {
    const onConfirm = vi.fn();
    render(
      <StatusRevertConfirmDialog
        open={true}
        currentStatus="resolved"
        requestedStatus="open"
        isPending={false}
        onCancel={() => {}}
        onConfirm={onConfirm}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "되돌리기" }));
    expect(onConfirm).toHaveBeenCalled();
  });

  it("invokes onCancel when 취소 clicked", () => {
    const onCancel = vi.fn();
    render(
      <StatusRevertConfirmDialog
        open={true}
        currentStatus="resolved"
        requestedStatus="open"
        isPending={false}
        onCancel={onCancel}
        onConfirm={() => {}}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "취소" }));
    expect(onCancel).toHaveBeenCalled();
  });

  it("disables buttons while pending", () => {
    render(
      <StatusRevertConfirmDialog
        open={true}
        currentStatus="resolved"
        requestedStatus="open"
        isPending={true}
        onCancel={() => {}}
        onConfirm={() => {}}
      />,
    );
    const confirm = screen.getByRole("button", { name: /처리 중/ }) as HTMLButtonElement;
    const cancel = screen.getByRole("button", { name: "취소" }) as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);
    expect(cancel.disabled).toBe(true);
  });
});
