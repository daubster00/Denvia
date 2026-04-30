import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { AnswerDetailDrawer } from "../AnswerDetailDrawer";
import type { FeedbackItem } from "../../api/analytics";

const sampleItem: FeedbackItem = {
  qa_log_id: 1001,
  question_text: "임플란트 보철물 선택 기준은 무엇인가요?",
  answer_text: "임플란트 보철물은 크라운·브릿지·틀니 세 종류입니다.",
  rating: "good",
  segment: "dentist",
  created_at: "2026-04-15T10:23:00+09:00",
};

describe("AnswerDetailDrawer", () => {
  it("item=null 이면 렌더하지 않음", () => {
    const { container } = render(
      <AnswerDetailDrawer item={null} onClose={vi.fn()} />
    );
    expect(container.firstChild).toBeNull();
  });

  it("질문/답변 전문 렌더", () => {
    render(<AnswerDetailDrawer item={sampleItem} onClose={vi.fn()} />);
    expect(screen.getByText(sampleItem.question_text)).toBeTruthy();
    expect(screen.getByText(sampleItem.answer_text!)).toBeTruthy();
  });

  it("aria-modal=true + role=dialog + aria-label", () => {
    render(<AnswerDetailDrawer item={sampleItem} onClose={vi.fn()} />);
    const dialog = screen.getByRole("dialog");
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    expect(dialog.getAttribute("aria-label")).toBe("답변 상세");
  });

  it("닫기 버튼 클릭 → onClose 호출", () => {
    const onClose = vi.fn();
    render(<AnswerDetailDrawer item={sampleItem} onClose={onClose} />);
    const closeBtn = screen.getByRole("button", { name: "Drawer 닫기" });
    fireEvent.click(closeBtn);
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("ESC 키 → onClose 호출", () => {
    const onClose = vi.fn();
    render(<AnswerDetailDrawer item={sampleItem} onClose={onClose} />);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("backdrop 클릭 → onClose 호출", () => {
    const onClose = vi.fn();
    const { container } = render(
      <AnswerDetailDrawer item={sampleItem} onClose={onClose} />
    );
    const backdrop = container.querySelector('[aria-hidden="true"]');
    expect(backdrop).not.toBeNull();
    fireEvent.click(backdrop!);
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("good rating — 👍 GOOD 텍스트 렌더", () => {
    render(<AnswerDetailDrawer item={sampleItem} onClose={vi.fn()} />);
    expect(screen.getByText("👍 GOOD")).toBeTruthy();
  });

  it("bad rating — 👎 BAD 텍스트 렌더", () => {
    const badItem = { ...sampleItem, rating: "bad" as const };
    render(<AnswerDetailDrawer item={badItem} onClose={vi.fn()} />);
    expect(screen.getByText("👎 BAD")).toBeTruthy();
  });
});
