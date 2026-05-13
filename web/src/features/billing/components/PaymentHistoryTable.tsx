"use client";

/**
 * PaymentHistoryTable — 마이페이지 결제 내역 테이블 + 해지/환불 진입 (Story 4.4 / FR27 / F-402).
 *
 * 구성:
 *   - 상단: SubscriptionStatusCard (active → 해지 / cancel_pending → 철회 / none → 미렌더)
 *   - 본문: 7컬럼 테이블 (결제일자/상품·기간/이메일/결제수단/금액/주문번호/상태) + 액션
 *   - 하단: per_page select + 이전/다음 + "현재/총" 페이지 표시
 *   - 0건: EmptyState — A-303(useUsageSummary.show_subscribe_button) ON 시 "구독 페이지로" 버튼
 *   - 에러: ErrorState — "새로고침" 버튼 (페이지 fallback 금지)
 *
 * 재사용:
 *   - Story 3.5: useCurrentSubscription / useResumeSubscription / SubscriptionStatusCard / CancelSubscriptionFlow
 *   - Story 3.6: RefundRequestPopup / RefundPaymentInfo
 *   - Story 4.3: useUsageSummary (A-303 토글 재사용 — round-trip 회피)
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";

import { useUsageSummary } from "@/features/account/hooks/useUsageSummary";

import { usePaymentHistory } from "../hooks/usePaymentHistory";
import type {
  PaymentHistoryItem,
  PaymentStatus,
  RefundPaymentInfo,
} from "../types";
import { PaymentStatusBadge } from "./PaymentStatusBadge";
import { RefundRequestPopup } from "./RefundRequestPopup";

import styles from "./PaymentHistoryTable.module.css";

const PER_PAGE_OPTIONS = [10, 20, 50] as const;
type PerPage = (typeof PER_PAGE_OPTIONS)[number];

function formatChargedAt(iso: string | null): string {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "-";
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  const hh = String(d.getHours()).padStart(2, "0");
  const mi = String(d.getMinutes()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd} ${hh}:${mi}`;
}

function formatPaymentDate(iso: string | null): string {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "-";
  return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, "0")}.${String(
    d.getDate()
  ).padStart(2, "0")}`;
}

function formatDetailDate(iso: string | null): string {
  const formatted = formatChargedAt(iso);
  if (formatted === "-") return "-";
  const d = new Date(iso ?? "");
  const days = ["일", "월", "화", "수", "목", "금", "토"];
  const date = formatted.slice(0, 10).replaceAll("-", ".");
  const time = formatted.slice(11);
  return `${date} (${days[d.getDay()]}) ${time}`;
}

function formatPeriod(start: string | null, end: string | null): string {
  if (!start || !end) return "-";
  const s = new Date(start);
  const e = new Date(end);
  if (Number.isNaN(s.getTime()) || Number.isNaN(e.getTime())) return "-";
  const fmt = (d: Date) =>
    `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
      d.getDate()
    ).padStart(2, "0")}`;
  return `${fmt(s)} ~ ${fmt(e)}`;
}

function formatPlanName(item: PaymentHistoryItem): string {
  if (item.subscription_period_start && item.subscription_period_end) {
    return "Pro 플랜 (월간)";
  }
  return "Pro 플랜";
}

function formatAmount(amount: number): string {
  return `${amount.toLocaleString("ko-KR")}원`;
}

function formatCard(
  company: string | null,
  last4: string | null
): string {
  if (!company && !last4) return "카드 정보 없음";
  if (!last4) return company ?? "카드 정보 없음";
  const co = company ?? "카드";
  return `${co} **** ${last4}`;
}

function isRefundable(status: PaymentStatus): boolean {
  return status === "success";
}

function statusText(status: PaymentStatus): string {
  switch (status) {
    case "success":
      return "결제 완료";
    case "refunded":
      return "환불 완료";
    case "refund_pending":
      return "환불 처리 중";
    case "failed":
      return "실패";
    case "pending":
      return "대기 중";
  }
}

function statusClass(status: PaymentStatus): string {
  switch (status) {
    case "refunded":
      return styles.itemStatusRefunded;
    case "refund_pending":
      return styles.itemStatusRefundPending;
    case "failed":
      return styles.itemStatusFailed;
    default:
      return "";
  }
}

export function PaymentHistoryTable() {
  const router = useRouter();
  const queryClient = useQueryClient();

  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = useState<PerPage>(20);
  const [selectedPaymentId, setSelectedPaymentId] = useState<number | null>(null);
  const [refundTarget, setRefundTarget] = useState<RefundPaymentInfo | null>(
    null
  );

  const { data, isLoading, isError, refetch, isFetching } = usePaymentHistory(
    page,
    perPage
  );
  const { data: usage } = useUsageSummary();

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = total === 0 ? 1 : Math.ceil(total / perPage);
  const selectedItem = useMemo(
    () => items.find((item) => item.payment_id === selectedPaymentId) ?? items[0] ?? null,
    [items, selectedPaymentId]
  );

  useEffect(() => {
    if (items.length === 0) {
      setSelectedPaymentId(null);
      return;
    }
    if (!items.some((item) => item.payment_id === selectedPaymentId)) {
      setSelectedPaymentId(items[0].payment_id);
    }
  }, [items, selectedPaymentId]);

  const handlePerPageChange = useCallback(
    (e: React.ChangeEvent<HTMLSelectElement>) => {
      const next = Number(e.target.value) as PerPage;
      setPerPage(next);
      setPage(1);
    },
    []
  );

  const handlePrev = useCallback(() => setPage((p) => Math.max(1, p - 1)), []);
  const handleNext = useCallback(() => setPage((p) => p + 1), []);

  const handleRefundClick = useCallback((item: PaymentHistoryItem) => {
    setRefundTarget({
      id: item.payment_id,
      amount_krw: item.amount_krw,
      // RefundRequestPopup의 RefundPaymentInfo.charged_at은 string 필수.
      // success 상태에서만 환불 버튼이 노출되므로 charged_at은 항상 존재한다.
      charged_at: item.charged_at ?? "",
      card_last4: item.card_last4,
    });
  }, []);

  const handleRefundClose = useCallback(() => setRefundTarget(null), []);

  const handleRefundSuccess = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["me", "payments"] });
    queryClient.invalidateQueries({ queryKey: ["billing", "current-subscription"] });
  }, [queryClient]);

  const showSubscribeButton = usage?.show_subscribe_button ?? false;

  return (
    <div className={styles.wrapper}>
      {isLoading && (
        <div className={styles.loading} role="status" aria-live="polite">
          <span className={styles.spinner} aria-hidden="true" />
          <span>결제 내역을 불러오는 중…</span>
        </div>
      )}

      {!isLoading && isError && (
        <div className={styles.errorState} role="alert">
          <p>결제 내역을 불러오지 못했습니다.</p>
          <button
            type="button"
            className={styles.refreshBtn}
            onClick={() => refetch()}
          >
            새로고침
          </button>
        </div>
      )}

      {!isLoading && !isError && total === 0 && (
        <div className={styles.emptyState}>
          <p className={styles.emptyTitle}>아직 결제 내역이 없어요</p>
          <p className={styles.emptyBody}>
            구독을 시작하면 결제 내역이 여기에 표시됩니다.
          </p>
          <ul className={styles.emptyHints} aria-label="결제 내역 안내">
            <li>결제가 완료되면 영수증과 상세 내역을 확인할 수 있어요.</li>
            <li>결제 내역은 취소 내역도 여기에 표시됩니다.</li>
          </ul>
          {showSubscribeButton && (
            <button
              type="button"
              className={styles.subscribeBtn}
              onClick={() => router.push("/subscribe")}
            >
              플랜 보러가기
            </button>
          )}
        </div>
      )}

      {!isLoading && !isError && total > 0 && selectedItem && (
        <div className={styles.historyLayout} aria-busy={isFetching ? "true" : "false"}>
          <div className={styles.historyList} aria-label="결제 내역 목록">
            {items.map((item) => {
              const selected = item.payment_id === selectedItem.payment_id;
              return (
                <button
                  key={item.payment_id}
                  type="button"
                  className={`${styles.historyItem} ${selected ? styles.historyItemSelected : ""}`}
                  onClick={() => setSelectedPaymentId(item.payment_id)}
                  aria-pressed={selected}
                >
                  <span className={styles.itemDate}>{formatPaymentDate(item.charged_at)}</span>
                  <span className={styles.itemPlan}>{formatPlanName(item)}</span>
                  <span className={styles.itemAmount}>{formatAmount(item.amount_krw)}</span>
                  <span className={`${styles.itemStatus} ${statusClass(item.status)}`}>{statusText(item.status)}</span>
                  <span className={styles.itemArrow} aria-hidden="true">›</span>
                </button>
              );
            })}

            <div className={styles.pagination}>
              <label className={styles.perPageLabel}>
                <span>표시 개수</span>
                <select
                  className={styles.perPageSelect}
                  value={perPage}
                  onChange={handlePerPageChange}
                  aria-label="페이지당 표시 개수"
                >
                  {PER_PAGE_OPTIONS.map((opt) => (
                    <option key={opt} value={opt}>
                      {opt}
                    </option>
                  ))}
                </select>
              </label>
              <div className={styles.pageNav}>
                <button
                  type="button"
                  className={styles.navBtn}
                  onClick={handlePrev}
                  disabled={page === 1}
                >
                  이전
                </button>
                <span className={styles.pageIndicator} aria-live="polite">
                  {page} / {totalPages}
                </span>
                <button
                  type="button"
                  className={styles.navBtn}
                  onClick={handleNext}
                  disabled={page * perPage >= total}
                >
                  다음
                </button>
              </div>
            </div>
          </div>

          <section className={styles.detailPanel} aria-label="결제 정보">
            <div className={styles.detailInfo}>
              <h3 className={styles.detailTitle}>결제 정보</h3>
              <dl className={styles.detailList}>
                <div>
                  <dt>결제일</dt>
                  <dd>{formatDetailDate(selectedItem.charged_at)}</dd>
                </div>
                <div>
                  <dt>결제 상품</dt>
                  <dd>{formatPlanName(selectedItem)}</dd>
                </div>
                <div>
                  <dt>결제 금액</dt>
                  <dd>{formatAmount(selectedItem.amount_krw)}</dd>
                </div>
                <div>
                  <dt>결제 수단</dt>
                  <dd>{formatCard(selectedItem.card_company, selectedItem.card_last4)}</dd>
                </div>
                <div>
                  <dt>승인번호</dt>
                  <dd>{selectedItem.provider_order_id}</dd>
                </div>
                <div>
                  <dt>결제 상태</dt>
                  <dd><PaymentStatusBadge status={selectedItem.status} /></dd>
                </div>
                <div>
                  <dt>이용 기간</dt>
                  <dd>{formatPeriod(selectedItem.subscription_period_start, selectedItem.subscription_period_end)}</dd>
                </div>
              </dl>
              {isRefundable(selectedItem.status) && (
                <button
                  type="button"
                  className={styles.refundBtn}
                  onClick={() => handleRefundClick(selectedItem)}
                >
                  환불 요청
                </button>
              )}
            </div>

            <aside className={styles.amountBox} aria-label="결제 금액 상세">
              <h3 className={styles.amountTitle}>결제 금액 상세</h3>
              <dl className={styles.amountList}>
                <div>
                  <dt>상품 금액</dt>
                  <dd>{formatAmount(selectedItem.amount_krw)}</dd>
                </div>
                <div>
                  <dt>부가가치세 (10%)</dt>
                  <dd>0원</dd>
                </div>
                <div>
                  <dt>쿠폰 할인</dt>
                  <dd>-0원</dd>
                </div>
                <div className={styles.amountTotal}>
                  <dt>총 결제 금액</dt>
                  <dd>{formatAmount(selectedItem.amount_krw)}</dd>
                </div>
              </dl>
            </aside>
          </section>
        </div>
      )}

      {refundTarget && (
        <RefundRequestPopup
          isOpen
          onClose={handleRefundClose}
          payment={refundTarget}
          onSuccess={handleRefundSuccess}
        />
      )}
    </div>
  );
}
