import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { AnomalyTable } from "../components/AnomalyTable";
import type {
  AnomalyEventItem,
  AnomalyListResponse,
} from "../api/anomaly";

function makeEvent(
  overrides: Partial<AnomalyEventItem> = {},
): AnomalyEventItem {
  return {
    id: 1,
    type: "rapid_followup_questions",
    target_user_id: 7,
    target_user_email_masked: "u**@example.com",
    ip: "1.2.3.4",
    ua: null,
    details: { count_in_window: 3 },
    status: "new",
    reviewed_by_admin_id: null,
    reviewed_at: null,
    created_at: "2026-05-01T03:00:00Z",
    ...overrides,
  };
}

function makeData(items: AnomalyEventItem[]): AnomalyListResponse {
  return { items, page: 1, per_page: 20, total: items.length };
}

const noop = () => {};

describe("AnomalyTable", () => {
  it("renders 6 columns including '상세' and a 상세보기 button per row", () => {
    render(
      <AnomalyTable
        data={makeData([makeEvent()])}
        isLoading={false}
        isError={false}
        page={1}
        perPage={20}
        onPageChange={noop}
        onShowDetail={noop}
        onRetry={noop}
      />,
    );
    expect(screen.getByText("발생일시")).toBeInTheDocument();
    expect(screen.getByText("분류")).toBeInTheDocument();
    expect(screen.getByText("대상 사용자")).toBeInTheDocument();
    expect(screen.getByText("IP")).toBeInTheDocument();
    expect(screen.getByText("상태")).toBeInTheDocument();
    expect(screen.getByText("상세")).toBeInTheDocument();
    expect(screen.getByTestId("anomaly-detail-1")).toBeInTheDocument();
  });

  it("invokes onShowDetail with the row item when 상세보기 clicked", () => {
    const onShowDetail = vi.fn();
    const event = makeEvent();
    render(
      <AnomalyTable
        data={makeData([event])}
        isLoading={false}
        isError={false}
        page={1}
        perPage={20}
        onPageChange={noop}
        onShowDetail={onShowDetail}
        onRetry={noop}
      />,
    );
    fireEvent.click(screen.getByTestId("anomaly-detail-1"));
    expect(onShowDetail).toHaveBeenCalledWith(event);
  });

  it("renders empty state when items is empty", () => {
    render(
      <AnomalyTable
        data={makeData([])}
        isLoading={false}
        isError={false}
        page={1}
        perPage={20}
        onPageChange={noop}
        onShowDetail={noop}
        onRetry={noop}
      />,
    );
    expect(screen.getByText("이상 이벤트가 없습니다.")).toBeInTheDocument();
  });

  it("renders error state with retry button", () => {
    const onRetry = vi.fn();
    render(
      <AnomalyTable
        data={undefined}
        isLoading={false}
        isError={true}
        page={1}
        perPage={20}
        onPageChange={noop}
        onShowDetail={noop}
        onRetry={onRetry}
      />,
    );
    fireEvent.click(screen.getByText("다시 시도"));
    expect(onRetry).toHaveBeenCalled();
  });
});
