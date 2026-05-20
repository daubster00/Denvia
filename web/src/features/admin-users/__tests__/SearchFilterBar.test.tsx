import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import {
  SearchFilterBar,
  type SearchFilters,
} from "../components/SearchFilterBar";

const baseValue: SearchFilters = {
  q: "",
  segment: null,
  subscription_status: null,
  blocked: null,
  created_from: "",
  created_to: "",
};

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("SearchFilterBar", () => {
  it("debounces q input changes by 300ms", () => {
    const onChange = vi.fn();
    render(
      <SearchFilterBar
        value={baseValue}
        onChange={onChange}
        onReset={vi.fn()}
        onRefresh={vi.fn()}
      />,
    );
    const input = screen.getByLabelText("사용자 통합 검색");
    fireEvent.change(input, { target: { value: "naver" } });

    // 즉시 호출 안 됨
    expect(onChange).not.toHaveBeenCalled();

    // 300ms 지나면 호출됨
    act(() => {
      vi.advanceTimersByTime(300);
    });
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ q: "naver" }),
    );
  });

  it("propagates segment select change immediately", () => {
    const onChange = vi.fn();
    render(
      <SearchFilterBar
        value={baseValue}
        onChange={onChange}
        onReset={vi.fn()}
        onRefresh={vi.fn()}
      />,
    );
    const select = screen.getByLabelText("가입유형 필터");
    fireEvent.change(select, { target: { value: "doctor" } });
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ segment: "doctor" }),
    );
  });

  it("invokes onReset when reset button clicked", () => {
    const onReset = vi.fn();
    render(
      <SearchFilterBar
        value={baseValue}
        onChange={vi.fn()}
        onReset={onReset}
        onRefresh={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "검색 조건 초기화" }));
    expect(onReset).toHaveBeenCalledOnce();
  });
});
