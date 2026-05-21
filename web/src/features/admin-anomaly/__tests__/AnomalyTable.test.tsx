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
  it("renders 6 columns + action buttons for status='new' rows", () => {
    render(
      <AnomalyTable
        data={makeData([makeEvent()])}
        isLoading={false}
        isError={false}
        page={1}
        perPage={20}
        onPageChange={noop}
        onApplyBlock={noop}
        onMarkReviewed={noop}
        onUnblock={noop}
        onRetry={noop}
      />,
    );
    expect(screen.getByText("발생일시")).toBeInTheDocument();
    expect(screen.getByText("분류")).toBeInTheDocument();
    expect(screen.getByText("대상 사용자")).toBeInTheDocument();
    expect(screen.getByText("IP")).toBeInTheDocument();
    expect(screen.getByText("상태")).toBeInTheDocument();
    expect(screen.getByText("액션")).toBeInTheDocument();
    expect(screen.getByTestId("anomaly-block-24h-1")).toBeInTheDocument();
    expect(screen.getByTestId("anomaly-block-7d-1")).toBeInTheDocument();
    expect(screen.getByTestId("anomaly-block-perm-1")).toBeInTheDocument();
    expect(screen.getByTestId("anomaly-review-1")).toBeInTheDocument();
  });

  it("hides 검토 완료 button on status='reviewed' rows", () => {
    render(
      <AnomalyTable
        data={makeData([makeEvent({ status: "reviewed" })])}
        isLoading={false}
        isError={false}
        page={1}
        perPage={20}
        onPageChange={noop}
        onApplyBlock={noop}
        onMarkReviewed={noop}
        onUnblock={noop}
        onRetry={noop}
      />,
    );
    expect(screen.queryByTestId("anomaly-review-1")).not.toBeInTheDocument();
    expect(screen.getByTestId("anomaly-block-24h-1")).toBeInTheDocument();
  });

  it("shows only 차단 해제 button on status='actioned' rows", () => {
    render(
      <AnomalyTable
        data={makeData([
          makeEvent({ status: "actioned", type: "concurrent_ip_login" }),
        ])}
        isLoading={false}
        isError={false}
        page={1}
        perPage={20}
        onPageChange={noop}
        onApplyBlock={noop}
        onMarkReviewed={noop}
        onUnblock={noop}
        onRetry={noop}
      />,
    );
    expect(screen.queryByTestId("anomaly-block-24h-1")).not.toBeInTheDocument();
    expect(screen.queryByTestId("anomaly-review-1")).not.toBeInTheDocument();
    expect(screen.getByTestId("anomaly-unblock-1")).toBeInTheDocument();
    expect(screen.getByText("차단 해제")).toBeInTheDocument();
    expect(screen.queryByText("차단 사용자 보기")).not.toBeInTheDocument();
  });

  it("shows 쿨다운 해제 label for rapid_followup_questions actioned row", () => {
    render(
      <AnomalyTable
        data={makeData([
          makeEvent({
            status: "actioned",
            type: "rapid_followup_questions",
          }),
        ])}
        isLoading={false}
        isError={false}
        page={1}
        perPage={20}
        onPageChange={noop}
        onApplyBlock={noop}
        onMarkReviewed={noop}
        onUnblock={noop}
        onRetry={noop}
      />,
    );
    expect(screen.getByTestId("anomaly-unblock-1")).toBeInTheDocument();
    expect(screen.getByText("쿨다운 해제")).toBeInTheDocument();
    expect(screen.queryByText("차단 해제")).not.toBeInTheDocument();
  });

  it("re-shows 24h/7d/영구 차단 buttons on status='unblocked' rows", () => {
    render(
      <AnomalyTable
        data={makeData([makeEvent({ status: "unblocked" })])}
        isLoading={false}
        isError={false}
        page={1}
        perPage={20}
        onPageChange={noop}
        onApplyBlock={noop}
        onMarkReviewed={noop}
        onUnblock={noop}
        onRetry={noop}
      />,
    );
    expect(screen.queryByTestId("anomaly-unblock-1")).not.toBeInTheDocument();
    expect(screen.queryByTestId("anomaly-review-1")).not.toBeInTheDocument();
    expect(screen.getByTestId("anomaly-block-24h-1")).toBeInTheDocument();
    expect(screen.getByTestId("anomaly-block-7d-1")).toBeInTheDocument();
    expect(screen.getByTestId("anomaly-block-perm-1")).toBeInTheDocument();
  });

  it("invokes onUnblock when 차단 해제 clicked on actioned row", () => {
    const onUnblock = vi.fn();
    const event = makeEvent({ status: "actioned" });
    render(
      <AnomalyTable
        data={makeData([event])}
        isLoading={false}
        isError={false}
        page={1}
        perPage={20}
        onPageChange={noop}
        onApplyBlock={noop}
        onMarkReviewed={noop}
        onUnblock={onUnblock}
        onRetry={noop}
      />,
    );
    fireEvent.click(screen.getByTestId("anomaly-unblock-1"));
    expect(onUnblock).toHaveBeenCalledWith(event);
  });

  it("invokes onApplyBlock with correct duration when 24h clicked", () => {
    const onApplyBlock = vi.fn();
    const event = makeEvent();
    render(
      <AnomalyTable
        data={makeData([event])}
        isLoading={false}
        isError={false}
        page={1}
        perPage={20}
        onPageChange={noop}
        onApplyBlock={onApplyBlock}
        onMarkReviewed={noop}
        onUnblock={noop}
        onRetry={noop}
      />,
    );
    fireEvent.click(screen.getByTestId("anomaly-block-24h-1"));
    expect(onApplyBlock).toHaveBeenCalledWith(event, 24);
  });

  it("invokes onApplyBlock with null for 영구", () => {
    const onApplyBlock = vi.fn();
    const event = makeEvent();
    render(
      <AnomalyTable
        data={makeData([event])}
        isLoading={false}
        isError={false}
        page={1}
        perPage={20}
        onPageChange={noop}
        onApplyBlock={onApplyBlock}
        onMarkReviewed={noop}
        onUnblock={noop}
        onRetry={noop}
      />,
    );
    fireEvent.click(screen.getByTestId("anomaly-block-perm-1"));
    expect(onApplyBlock).toHaveBeenCalledWith(event, null);
  });

  it("invokes onMarkReviewed when 검토 완료 clicked", () => {
    const onMarkReviewed = vi.fn();
    const event = makeEvent();
    render(
      <AnomalyTable
        data={makeData([event])}
        isLoading={false}
        isError={false}
        page={1}
        perPage={20}
        onPageChange={noop}
        onApplyBlock={noop}
        onMarkReviewed={onMarkReviewed}
        onUnblock={noop}
        onRetry={noop}
      />,
    );
    fireEvent.click(screen.getByTestId("anomaly-review-1"));
    expect(onMarkReviewed).toHaveBeenCalledWith(event);
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
        onApplyBlock={noop}
        onMarkReviewed={noop}
        onUnblock={noop}
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
        onApplyBlock={noop}
        onMarkReviewed={noop}
        onUnblock={noop}
        onRetry={onRetry}
      />,
    );
    fireEvent.click(screen.getByText("다시 시도"));
    expect(onRetry).toHaveBeenCalled();
  });
});
