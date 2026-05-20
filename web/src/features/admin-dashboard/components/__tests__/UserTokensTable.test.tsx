import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { UserTokensTable } from "../UserTokensTable";
import { UserTokensRow } from "../../api/analytics";

// next/navigation mock
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

const sampleRows: UserTokensRow[] = [
  {
    user_id: 42,
    email: "alice@example.com",
    segment: "dental_student",
    total_input_tokens: 15000,
    total_output_tokens: 8000,
    total_cost_usd: "0.245100",
    total_cost_krw: 343,
    avg_cost_per_question_krw: 20,
    question_count: 17,
    avg_cost_per_question: "0.014418",
  },
  {
    user_id: 43,
    email: "bob@example.com",
    segment: null,
    total_input_tokens: 3000,
    total_output_tokens: 1500,
    total_cost_usd: "0.050000",
    total_cost_krw: 70,
    avg_cost_per_question_krw: 14,
    question_count: 5,
    avg_cost_per_question: "0.010000",
  },
];

describe("UserTokensTable", () => {
  it("EmptyState — items 빈 배열 시 안내 메시지 표시", () => {
    render(
      <UserTokensTable
        items={[]}
        page={1}
        perPage={50}
        total={0}
        onPageChange={vi.fn()}
      />
    );
    expect(
      screen.getByText(/이번 기간에 질의 기록이 없습니다/i)
    ).toBeTruthy();
  });

  it("행 렌더 — 이메일, KRW 환산 비용 표시", () => {
    render(
      <UserTokensTable
        items={sampleRows}
        page={1}
        perPage={50}
        total={2}
        onPageChange={vi.fn()}
      />
    );
    expect(screen.getByText("alice@example.com")).toBeTruthy();
    expect(screen.getByText("bob@example.com")).toBeTruthy();
    expect(screen.getByText("₩343")).toBeTruthy();
  });

  it("이전/다음 페이지 버튼 aria-label", () => {
    render(
      <UserTokensTable
        items={sampleRows}
        page={2}
        perPage={2}
        total={10}
        onPageChange={vi.fn()}
      />
    );
    expect(screen.getByLabelText("이전 페이지")).toBeTruthy();
    expect(screen.getByLabelText("다음 페이지")).toBeTruthy();
  });

  it("onPageChange 호출 — 다음 페이지 클릭", () => {
    const onPageChange = vi.fn();
    render(
      <UserTokensTable
        items={sampleRows}
        page={1}
        perPage={2}
        total={10}
        onPageChange={onPageChange}
      />
    );
    fireEvent.click(screen.getByLabelText("다음 페이지"));
    expect(onPageChange).toHaveBeenCalledWith(2);
  });

  it("page=1 이면 이전 버튼 비활성", () => {
    render(
      <UserTokensTable
        items={sampleRows}
        page={1}
        perPage={50}
        total={2}
        onPageChange={vi.fn()}
      />
    );
    expect(
      (screen.getByLabelText("이전 페이지") as HTMLButtonElement).disabled
    ).toBe(true);
  });

  it("마지막 페이지이면 다음 버튼 비활성", () => {
    render(
      <UserTokensTable
        items={sampleRows}
        page={1}
        perPage={50}
        total={2}
        onPageChange={vi.fn()}
      />
    );
    expect(
      (screen.getByLabelText("다음 페이지") as HTMLButtonElement).disabled
    ).toBe(true);
  });

  it("segment null — '—' 표시", () => {
    render(
      <UserTokensTable
        items={sampleRows}
        page={1}
        perPage={50}
        total={2}
        onPageChange={vi.fn()}
      />
    );
    const dashes = screen.getAllByText("—");
    expect(dashes.length).toBeGreaterThanOrEqual(1);
  });
});
