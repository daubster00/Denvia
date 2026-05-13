import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { SynonymGroupForm } from "../SynonymGroupForm";

describe("SynonymGroupForm", () => {
  it("초기 렌더: 대표어 input + 동의어 chip input 표시", () => {
    render(
      <SynonymGroupForm
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByLabelText("대표어")).toBeDefined();
    expect(screen.getByText("동의어 (Enter로 추가)")).toBeDefined();
  });

  it("initial 값으로 폼이 채워진다", () => {
    render(
      <SynonymGroupForm
        initial={{
          id: 1,
          canonical_term: "광중합기",
          synonyms: ["큐링기", "큐어링"],
          updated_at: "2026-05-12T00:00:00Z",
        }}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    const canonical = screen.getByLabelText("대표어") as HTMLInputElement;
    expect(canonical.value).toBe("광중합기");
    expect(screen.getByText("큐링기")).toBeDefined();
    expect(screen.getByText("큐어링")).toBeDefined();
  });

  it("Enter 키로 동의어 칩 추가", () => {
    render(<SynonymGroupForm onSubmit={vi.fn()} onCancel={vi.fn()} />);

    // 대표어 먼저 입력 (required)
    fireEvent.change(screen.getByLabelText("대표어"), {
      target: { value: "광중합기" },
    });

    // 칩 입력 영역의 input은 라벨 없는 input 두 번째 (또는 placeholder로 찾기)
    const chipInputs = screen
      .getAllByRole("textbox")
      .filter((el) => el !== screen.getByLabelText("대표어"));
    const chipInput = chipInputs[0];
    fireEvent.change(chipInput, { target: { value: "큐링기" } });
    fireEvent.keyDown(chipInput, { key: "Enter" });

    expect(screen.getByText("큐링기")).toBeDefined();
  });

  it("× 클릭으로 칩 제거", () => {
    render(
      <SynonymGroupForm
        initial={{
          id: 1,
          canonical_term: "광중합기",
          synonyms: ["큐링기"],
          updated_at: "2026-05-12T00:00:00Z",
        }}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
      />,
    );

    expect(screen.getByText("큐링기")).toBeDefined();
    fireEvent.click(screen.getByLabelText("큐링기 제거"));
    expect(screen.queryByText("큐링기")).toBeNull();
  });

  it("점유된 동의어를 입력하면 노란 경고 표시", () => {
    const occupied = new Map<string, { id: number; canonicalTerm: string }>();
    occupied.set("큐링기", { id: 99, canonicalTerm: "광중합기" });

    render(
      <SynonymGroupForm
        occupiedTerms={occupied}
        initial={{
          id: 1,
          canonical_term: "다른그룹",
          synonyms: ["큐링기"],
          updated_at: "2026-05-12T00:00:00Z",
        }}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
      />,
    );

    const chip = screen.getByText("큐링기").closest("span")!;
    // 충돌 클래스는 .chipConflict — CSS modules는 해시되므로 title attribute로 확인
    expect(chip.getAttribute("title")).toContain("이미 그룹 '광중합기'");
  });

  it("대표어 점유 충돌 시 노란 경고 배너 표시", () => {
    const occupied = new Map<string, { id: number; canonicalTerm: string }>();
    occupied.set("큐링기", { id: 99, canonicalTerm: "다른그룹" });

    render(
      <SynonymGroupForm
        occupiedTerms={occupied}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByLabelText("대표어"), {
      target: { value: "큐링기" },
    });

    expect(
      screen.getByText(/이미 그룹.*다른그룹.*에 있는/),
    ).toBeDefined();
  });

  it("취소 버튼 → onCancel 호출", () => {
    const onCancel = vi.fn();
    render(<SynonymGroupForm onSubmit={vi.fn()} onCancel={onCancel} />);
    fireEvent.click(screen.getByText("취소"));
    expect(onCancel).toHaveBeenCalled();
  });
});
