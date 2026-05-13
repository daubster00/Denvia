import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ManualKillSwitchActivateDialog } from "@/features/admin-finance/components/ManualKillSwitchActivateDialog";
import * as killswitchApi from "@/features/admin-finance/api/killswitch";

function renderDialog(open: boolean, onClose = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return {
    onClose,
    ...render(
      <QueryClientProvider client={qc}>
        <ManualKillSwitchActivateDialog open={open} onClose={onClose} />
      </QueryClientProvider>,
    ),
  };
}

describe("ManualKillSwitchActivateDialog", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("open=false 일 때 렌더되지 않음", () => {
    renderDialog(false);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("open=true 일 때 헤더 + 사유 textarea + 체크박스 + 두 버튼 노출", () => {
    renderDialog(true);
    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(screen.getByText(/전체 정지 발동 확인/)).toBeTruthy();
    expect(screen.getByLabelText(/발동 사유/)).toBeTruthy();
    expect(screen.getByText(/이해했습니다/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "취소" })).toBeTruthy();
    expect(screen.getByRole("button", { name: /전체 정지 발동/ })).toBeTruthy();
  });

  it("X 닫기 버튼 없음 (UX-DR27 의도적 마찰)", () => {
    renderDialog(true);
    // role=dialog 안에 close/X 버튼이 없는지 검증
    const dialog = screen.getByRole("dialog");
    const closeBtns = dialog.querySelectorAll('[aria-label*="닫기"]');
    expect(closeBtns.length).toBe(0);
  });

  it("사유 4자 미만 → 발동 버튼 disabled", () => {
    renderDialog(true);
    const textarea = screen.getByLabelText(/발동 사유/) as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "abc" } });
    const checkbox = screen.getByRole("checkbox");
    fireEvent.click(checkbox);
    const submit = screen.getByRole("button", { name: /전체 정지 발동/ });
    expect(submit.hasAttribute("disabled")).toBe(true);
  });

  it("사유 4자 이상 + 체크박스 미체크 → 발동 버튼 disabled", () => {
    renderDialog(true);
    const textarea = screen.getByLabelText(/발동 사유/) as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "OpenAI 장애" } });
    const submit = screen.getByRole("button", { name: /전체 정지 발동/ });
    expect(submit.hasAttribute("disabled")).toBe(true);
  });

  it("사유 4자 이상 + 체크박스 체크 → 발동 버튼 활성", () => {
    renderDialog(true);
    const textarea = screen.getByLabelText(/발동 사유/) as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "OpenAI 장애 대응 — 11/24" } });
    const checkbox = screen.getByRole("checkbox");
    fireEvent.click(checkbox);
    const submit = screen.getByRole("button", { name: /전체 정지 발동/ });
    expect(submit.hasAttribute("disabled")).toBe(false);
  });

  it("발동 성공 → API 호출 + onClose 호출", async () => {
    const spy = vi
      .spyOn(killswitchApi, "activateManualKillswitch")
      .mockResolvedValue({
        id: 1,
        activated_at: "2026-05-07T05:00:00Z",
        mode: "manual_total",
        active: true,
      });
    const onClose = vi.fn();
    renderDialog(true, onClose);
    fireEvent.change(screen.getByLabelText(/발동 사유/), {
      target: { value: "OpenAI 장애 대응 — 11/24 14:00" },
    });
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: /전체 정지 발동/ }));

    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect(spy.mock.calls[0][0]).toContain("OpenAI 장애 대응");
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });
});
