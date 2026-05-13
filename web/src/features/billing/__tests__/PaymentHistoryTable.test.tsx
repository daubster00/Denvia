/** PaymentHistoryTable 단위 테스트 — Story 4.4. */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";

import type {
  CurrentSubscription,
  PaymentHistoryItem,
  PaymentHistoryResponse,
  PaymentStatus,
} from "../types";

const mockFetchPaymentHistory = vi.fn();
const mockFetchCurrentSubscription = vi.fn();
const mockFetchUsageSummary = vi.fn();
const mockResumeSubscription = vi.fn();
const mockRouterPush = vi.fn();

vi.mock("../api", () => ({
  fetchPaymentHistory: (...a: unknown[]) => mockFetchPaymentHistory(...a),
  fetchCurrentSubscription: () => mockFetchCurrentSubscription(),
  resumeSubscription: () => mockResumeSubscription(),
}));

vi.mock("@/features/account/api", () => ({
  fetchUsageSummary: () => mockFetchUsageSummary(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockRouterPush }),
}));

import { PaymentHistoryTable } from "../components/PaymentHistoryTable";

function wrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: qc }, children);
}

function renderTable() {
  return render(<PaymentHistoryTable />, { wrapper: wrapper() });
}

const subActive: CurrentSubscription = {
  status: "active",
  started_at: "2026-04-01T00:00:00+00:00",
  current_period_end: "2026-05-01T00:00:00+00:00",
  next_charge_at: "2026-05-01T00:00:00+00:00",
  canceled_at: null,
  cancel_reason: null,
};

const subNone: CurrentSubscription = {
  status: "none",
  started_at: null,
  current_period_end: null,
  next_charge_at: null,
  canceled_at: null,
  cancel_reason: null,
};

const subCancelPending: CurrentSubscription = {
  status: "cancel_pending",
  started_at: "2026-04-01T00:00:00+00:00",
  current_period_end: "2026-05-01T00:00:00+00:00",
  next_charge_at: null,
  canceled_at: "2026-04-15T00:00:00+00:00",
  cancel_reason: "test",
};

function makeItem(
  overrides: Partial<PaymentHistoryItem> = {}
): PaymentHistoryItem {
  return {
    payment_id: 1,
    charged_at: "2026-04-30T05:23:11+00:00",
    subscription_period_start: "2026-04-30T00:00:00+00:00",
    subscription_period_end: "2026-05-29T23:59:59+00:00",
    buyer_email: "user@example.com",
    card_last4: "1234",
    card_company: "현대",
    amount_krw: 9900,
    provider_order_id: "sub-1-2026-04-30",
    status: "success" as PaymentStatus,
    ...overrides,
  };
}

function makeResponse(
  items: PaymentHistoryItem[],
  total = items.length,
  page = 1,
  perPage = 20
): PaymentHistoryResponse {
  return { items, total, page, per_page: perPage };
}

beforeEach(() => {
  vi.clearAllMocks();
  mockFetchUsageSummary.mockResolvedValue({
    month_question_count: 0,
    daily_used: 0,
    daily_limit: 0,
    daily_remaining: 0,
    daily_reset_at: "",
    subscription_status: "free",
    segment: null,
    years_of_experience: null,
    show_subscribe_button: true,
  });
});

describe("PaymentHistoryTable — EmptyState (AC-8)", () => {
  it("total=0 + show_subscribe_button=true → '플랜 보러가기' 버튼 노출", async () => {
    mockFetchCurrentSubscription.mockResolvedValue(subNone);
    mockFetchPaymentHistory.mockResolvedValue(makeResponse([], 0));

    renderTable();

    await waitFor(() =>
      expect(screen.getByText("아직 결제 내역이 없어요")).toBeDefined()
    );
    expect(screen.getByText("플랜 보러가기")).toBeDefined();
  });

  it("total=0 + show_subscribe_button=false → 구독 버튼 미렌더 (DOM 자체)", async () => {
    mockFetchUsageSummary.mockResolvedValue({
      month_question_count: 0,
      daily_used: 0,
      daily_limit: 0,
      daily_remaining: 0,
      daily_reset_at: "",
      subscription_status: "free",
      segment: null,
      years_of_experience: null,
      show_subscribe_button: false,
    });
    mockFetchCurrentSubscription.mockResolvedValue(subNone);
    mockFetchPaymentHistory.mockResolvedValue(makeResponse([], 0));

    renderTable();

    await waitFor(() =>
      expect(screen.getByText("아직 결제 내역이 없어요")).toBeDefined()
    );
    expect(screen.queryByText("플랜 보러가기")).toBeNull();
  });

  it("'플랜 보러가기' 클릭 → router.push('/subscribe')", async () => {
    mockFetchCurrentSubscription.mockResolvedValue(subNone);
    mockFetchPaymentHistory.mockResolvedValue(makeResponse([], 0));

    renderTable();

    await waitFor(() => screen.getByText("플랜 보러가기"));
    fireEvent.click(screen.getByText("플랜 보러가기"));
    expect(mockRouterPush).toHaveBeenCalledWith("/subscribe");
  });
});

describe("PaymentHistoryTable — 1건 row 표시 (AC-2)", () => {
  it("7컬럼 표시 (status=success, 자가 환불 버튼은 v1.1에서 폐지)", async () => {
    mockFetchCurrentSubscription.mockResolvedValue(subNone);
    mockFetchPaymentHistory.mockResolvedValue(makeResponse([makeItem()]));

    renderTable();

    await waitFor(() =>
      expect(screen.getByText(/sub-1-2026-04-30/)).toBeDefined()
    );
    expect(screen.getAllByText("9,900원").length).toBeGreaterThan(0);
    expect(screen.getByText("현대 **** 1234")).toBeDefined();
    expect(screen.getAllByText("결제 완료").length).toBeGreaterThan(0);
    expect(screen.queryByText("환불 요청")).toBeNull();
  });

  it("status=refunded → '환불 완료' 뱃지", async () => {
    mockFetchCurrentSubscription.mockResolvedValue(subNone);
    mockFetchPaymentHistory.mockResolvedValue(
      makeResponse([makeItem({ status: "refunded" })])
    );

    renderTable();

    await waitFor(() =>
      expect(screen.getAllByText("환불 완료").length).toBeGreaterThan(0)
    );
    expect(screen.queryByText("환불 요청")).toBeNull();
  });

  it("status=refund_pending → '환불 처리 중' 뱃지", async () => {
    mockFetchCurrentSubscription.mockResolvedValue(subNone);
    mockFetchPaymentHistory.mockResolvedValue(
      makeResponse([makeItem({ status: "refund_pending" })])
    );

    renderTable();

    await waitFor(() =>
      expect(screen.getAllByText("환불 처리 중").length).toBeGreaterThan(0)
    );
    expect(screen.queryByText("환불 요청")).toBeNull();
  });

  it("card_last4=null → '카드 정보 없음' 표기", async () => {
    mockFetchCurrentSubscription.mockResolvedValue(subNone);
    mockFetchPaymentHistory.mockResolvedValue(
      makeResponse([
        makeItem({ card_last4: null, card_company: null }),
      ])
    );

    renderTable();

    await waitFor(() =>
      expect(screen.getByText("카드 정보 없음")).toBeDefined()
    );
  });

  it("status=failed → '실패' 뱃지", async () => {
    mockFetchCurrentSubscription.mockResolvedValue(subNone);
    mockFetchPaymentHistory.mockResolvedValue(
      makeResponse([makeItem({ status: "failed" })])
    );

    renderTable();

    await waitFor(() =>
      expect(screen.getAllByText("실패").length).toBeGreaterThan(0)
    );
    expect(screen.queryByText("환불 요청")).toBeNull();
  });
});

describe("PaymentHistoryTable — Pagination (AC-5)", () => {
  it("이전 버튼은 page=1에서 disabled", async () => {
    mockFetchCurrentSubscription.mockResolvedValue(subNone);
    mockFetchPaymentHistory.mockResolvedValue(
      makeResponse([makeItem()], 47, 1, 20)
    );

    renderTable();

    await waitFor(() => screen.getByText("이전"));
    const prev = screen.getByText("이전") as HTMLButtonElement;
    expect(prev.disabled).toBe(true);
  });

  it("다음 버튼: page * per_page >= total 이면 disabled", async () => {
    mockFetchCurrentSubscription.mockResolvedValue(subNone);
    mockFetchPaymentHistory.mockResolvedValue(
      makeResponse([makeItem()], 5, 1, 20)
    );

    renderTable();

    await waitFor(() => screen.getByText("다음"));
    const next = screen.getByText("다음") as HTMLButtonElement;
    expect(next.disabled).toBe(true);
  });

  it("per_page 변경 시 page=1로 리셋 + fetch 재호출", async () => {
    mockFetchCurrentSubscription.mockResolvedValue(subNone);
    mockFetchPaymentHistory.mockResolvedValue(
      makeResponse([makeItem()], 100, 1, 20)
    );

    renderTable();

    await waitFor(() => screen.getByLabelText("페이지당 표시 개수"));
    const select = screen.getByLabelText(
      "페이지당 표시 개수"
    ) as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "50" } });

    await waitFor(() =>
      expect(mockFetchPaymentHistory).toHaveBeenCalledWith(1, 50)
    );
  });

  it("페이지 표시: '{page} / {totalPages}' 형식", async () => {
    mockFetchCurrentSubscription.mockResolvedValue(subNone);
    mockFetchPaymentHistory.mockResolvedValue(
      makeResponse([makeItem()], 47, 1, 20)
    );

    renderTable();

    await waitFor(() => expect(screen.getByText("1 / 3")).toBeDefined());
  });
});

describe("PaymentHistoryTable — 구독 관리 버튼 위치", () => {
  it("status=active → 결제 내역에서는 '구독 해지' 버튼 미노출", async () => {
    mockFetchCurrentSubscription.mockResolvedValue(subActive);
    mockFetchPaymentHistory.mockResolvedValue(makeResponse([], 0));

    renderTable();

    await waitFor(() => screen.getByText("아직 결제 내역이 없어요"));
    expect(screen.queryByText("구독 해지")).toBeNull();
  });

  it("status=cancel_pending → 결제 내역에서는 '해지 철회' 버튼 미노출", async () => {
    mockFetchCurrentSubscription.mockResolvedValue(subCancelPending);
    mockFetchPaymentHistory.mockResolvedValue(makeResponse([], 0));

    renderTable();

    await waitFor(() => screen.getByText("아직 결제 내역이 없어요"));
    expect(screen.queryByText("해지 철회")).toBeNull();
  });

  it("status=none → SubscriptionStatusCard 미렌더", async () => {
    mockFetchCurrentSubscription.mockResolvedValue(subNone);
    mockFetchPaymentHistory.mockResolvedValue(makeResponse([], 0));

    renderTable();

    await waitFor(() => screen.getByText("아직 결제 내역이 없어요"));
    expect(screen.queryByText("구독 해지")).toBeNull();
    expect(screen.queryByText("해지 철회")).toBeNull();
  });
});

describe("PaymentHistoryTable — ErrorState (AC-5)", () => {
  it("fetch 실패 시 ErrorState + '새로고침' 버튼 노출", async () => {
    mockFetchCurrentSubscription.mockResolvedValue(subNone);
    mockFetchPaymentHistory.mockRejectedValue(new Error("network"));

    renderTable();

    await waitFor(
      () =>
        expect(
          screen.getByText("결제 내역을 불러오지 못했습니다.")
        ).toBeDefined(),
      { timeout: 2000 }
    );
    expect(screen.getByText("새로고침")).toBeDefined();
  });
});
