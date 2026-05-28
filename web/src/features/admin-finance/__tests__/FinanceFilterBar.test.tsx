import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import {
  FinanceFilterBar,
  type FinanceFilterValues,
} from "@/features/admin-finance/components/FinanceFilterBar";

const baseValues: FinanceFilterValues = {
  from: "",
  to: "",
  statusIn: [],
  errorCode: "",
  userId: undefined,
};

describe("FinanceFilterBar", () => {
  it("from/to 변경 시 onChange 호출", () => {
    const onChange = vi.fn();
    render(<FinanceFilterBar {...baseValues} onChange={onChange} />);
    const fromInput = screen.getByLabelText("시작일") as HTMLInputElement;
    fireEvent.change(fromInput, { target: { value: "2026-05-01" } });
    expect(onChange).toHaveBeenCalledWith({
      ...baseValues,
      from: "2026-05-01",
    });
  });

  it("결제 상태 체크박스 토글 시 statusIn 갱신", () => {
    const onChange = vi.fn();
    render(<FinanceFilterBar {...baseValues} onChange={onChange} />);
    const successCheckbox = screen.getByLabelText("결제 완료") as HTMLInputElement;
    fireEvent.click(successCheckbox);
    expect(onChange).toHaveBeenCalledWith({
      ...baseValues,
      statusIn: ["success"],
    });
  });

  it("PG 에러 코드 입력 시 onChange 호출", () => {
    const onChange = vi.fn();
    render(<FinanceFilterBar {...baseValues} onChange={onChange} />);
    const input = screen.getByLabelText("PG 에러 코드") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "EXPIRED_CARD" } });
    expect(onChange).toHaveBeenCalledWith({
      ...baseValues,
      errorCode: "EXPIRED_CARD",
    });
  });

  it("사용자 ID 입력 — 빈 값은 undefined", () => {
    const onChange = vi.fn();
    render(
      <FinanceFilterBar
        {...baseValues}
        userId="42"
        onChange={onChange}
      />,
    );
    const input = screen.getByLabelText("사용자 ID") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "" } });
    expect(onChange).toHaveBeenCalledWith({
      ...baseValues,
      userId: undefined,
    });
  });

  it("사용자 ID 입력 — 이메일도 onChange로 그대로 전달", () => {
    const onChange = vi.fn();
    render(<FinanceFilterBar {...baseValues} onChange={onChange} />);
    const input = screen.getByLabelText("사용자 ID") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "user@example.com" } });
    expect(onChange).toHaveBeenCalledWith({
      ...baseValues,
      userId: "user@example.com",
    });
  });

  it("seed 에러 코드 + page 추출 코드가 datalist에 노출", () => {
    const { container } = render(
      <FinanceFilterBar
        {...baseValues}
        errorCodeOptions={["DYNAMIC_CODE"]}
        onChange={vi.fn()}
      />,
    );
    const options = container.querySelectorAll("datalist option");
    const values = Array.from(options).map((o) => o.getAttribute("value"));
    expect(values).toContain("DYNAMIC_CODE");
    expect(values).toContain("INVALID_CARD_NUMBER"); // seed
  });
});
