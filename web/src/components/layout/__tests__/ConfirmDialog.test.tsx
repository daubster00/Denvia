import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ConfirmDialog } from "../ConfirmDialog";

const base = {
  open: true,
  title: "삭제하시겠습니까?",
  onConfirm: vi.fn(),
  onCancel: vi.fn(),
};

describe("ConfirmDialog", () => {
  it("open=false 이면 렌더 없음", () => {
    render(<ConfirmDialog {...base} open={false} />);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("title·description 렌더", () => {
    render(<ConfirmDialog {...base} description="설명 텍스트" />);
    expect(screen.getByText("삭제하시겠습니까?")).toBeDefined();
    expect(screen.getByText("설명 텍스트")).toBeDefined();
  });

  it("확인 버튼 클릭 → onConfirm 호출", () => {
    const onConfirm = vi.fn();
    render(<ConfirmDialog {...base} confirmLabel="삭제" onConfirm={onConfirm} />);
    fireEvent.click(screen.getByText("삭제"));
    expect(onConfirm).toHaveBeenCalledOnce();
  });

  it("취소 버튼 클릭 → onCancel 호출", () => {
    const onCancel = vi.fn();
    render(<ConfirmDialog {...base} onCancel={onCancel} />);
    fireEvent.click(screen.getByText("취소"));
    expect(onCancel).toHaveBeenCalledOnce();
  });

  it("isSubmitting=true → 확인 버튼 disabled, '처리 중…' 텍스트", () => {
    render(<ConfirmDialog {...base} confirmLabel="삭제" isSubmitting />);
    const confirmBtn = screen.getByText("처리 중…") as HTMLButtonElement;
    expect(confirmBtn.disabled).toBe(true);
  });

  it("isSubmitting=true → 확인 버튼 클릭해도 onConfirm 호출 안 됨", () => {
    const onConfirm = vi.fn();
    render(<ConfirmDialog {...base} confirmLabel="삭제" isSubmitting onConfirm={onConfirm} />);
    const confirmBtn = screen.getByText("처리 중…") as HTMLButtonElement;
    fireEvent.click(confirmBtn);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("isSubmitting=false → 확인 버튼 활성화", () => {
    render(<ConfirmDialog {...base} confirmLabel="삭제" isSubmitting={false} />);
    const confirmBtn = screen.getByText("삭제") as HTMLButtonElement;
    expect(confirmBtn.disabled).toBe(false);
  });

  it("errorMessage → 에러 메시지 렌더", () => {
    render(<ConfirmDialog {...base} errorMessage="삭제에 실패했습니다." />);
    expect(screen.getByText("삭제에 실패했습니다.")).toBeDefined();
  });

  it("errorMessage 없으면 에러 영역 미표시", () => {
    render(<ConfirmDialog {...base} />);
    expect(screen.queryByText("삭제에 실패했습니다.")).toBeNull();
  });

  it("ESC 키 → onCancel 호출", () => {
    const onCancel = vi.fn();
    render(<ConfirmDialog {...base} onCancel={onCancel} />);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onCancel).toHaveBeenCalledOnce();
  });
});
