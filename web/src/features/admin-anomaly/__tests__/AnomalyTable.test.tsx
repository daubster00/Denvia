import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { AnomalyTable } from "../components/AnomalyTable";
import type {
  AnomalyEventItem,
  AnomalyListResponse,
} from "../api/anomaly";

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

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
    occurrence_count: 1,
    last_occurred_at: "2026-05-01T03:00:00Z",
    user_blocked_now: false,
    user_auto_throttled_now: false,
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
      { wrapper },
    );
    expect(screen.getByText("발생일시")).toBeTruthy();
    expect(screen.getByText("분류")).toBeTruthy();
    expect(screen.getByText("대상 사용자")).toBeTruthy();
    expect(screen.getByText("IP")).toBeTruthy();
    expect(screen.getByText("상태")).toBeTruthy();
    expect(screen.getByText("상세")).toBeTruthy();
    expect(screen.getByTestId("anomaly-detail-1")).toBeTruthy();
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
      { wrapper },
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
      { wrapper },
    );
    expect(screen.getByText("이상 이벤트가 없습니다.")).toBeTruthy();
  });

  it("렌더링: 차단X + 자동제한X + status=new → '검토필요'", () => {
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
      { wrapper },
    );
    const el = screen.getByTestId("anomaly-status-needs-review");
    expect(el).toBeDefined();
    expect(el.textContent).toBe("검토필요");
  });

  it("렌더링: 차단X + 자동제한O → '자동제한'", () => {
    render(
      <AnomalyTable
        data={makeData([makeEvent({ user_auto_throttled_now: true })])}
        isLoading={false}
        isError={false}
        page={1}
        perPage={20}
        onPageChange={noop}
        onShowDetail={noop}
        onRetry={noop}
      />,
      { wrapper },
    );
    const el = screen.getByTestId("anomaly-status-auto-throttle");
    expect(el).toBeDefined();
    expect(el.textContent).toBe("자동제한");
  });

  it("렌더링: 차단O + 자동제한X → '차단'", () => {
    render(
      <AnomalyTable
        data={makeData([makeEvent({ user_blocked_now: true, status: "actioned" })])}
        isLoading={false}
        isError={false}
        page={1}
        perPage={20}
        onPageChange={noop}
        onShowDetail={noop}
        onRetry={noop}
      />,
      { wrapper },
    );
    const el = screen.getByTestId("anomaly-status-blocked");
    expect(el).toBeDefined();
    expect(el.textContent).toBe("차단");
  });

  it("렌더링: 차단O + 자동제한O → '차단 및 제한'", () => {
    render(
      <AnomalyTable
        data={makeData([
          makeEvent({
            user_blocked_now: true,
            user_auto_throttled_now: true,
            status: "actioned",
          }),
        ])}
        isLoading={false}
        isError={false}
        page={1}
        perPage={20}
        onPageChange={noop}
        onShowDetail={noop}
        onRetry={noop}
      />,
      { wrapper },
    );
    const el = screen.getByTestId("anomaly-status-blocked-throttled");
    expect(el).toBeDefined();
    expect(el.textContent).toBe("차단 및 제한");
  });

  it("렌더링: 둘 다 X + status≠new (한 번 걸렸다 풀린 상태) → '해제'", () => {
    render(
      <AnomalyTable
        data={makeData([makeEvent({ status: "unblocked" })])}
        isLoading={false}
        isError={false}
        page={1}
        perPage={20}
        onPageChange={noop}
        onShowDetail={noop}
        onRetry={noop}
      />,
      { wrapper },
    );
    const el = screen.getByTestId("anomaly-status-resolved");
    expect(el).toBeDefined();
    expect(el.textContent).toBe("해제");
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
      { wrapper },
    );
    fireEvent.click(screen.getByText("다시 시도"));
    expect(onRetry).toHaveBeenCalled();
  });
});
