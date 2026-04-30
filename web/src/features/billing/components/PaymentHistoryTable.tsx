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

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";

import { useUsageSummary } from "@/features/account/hooks/useUsageSummary";

import { useCurrentSubscription } from "../hooks/useCurrentSubscription";
import { usePaymentHistory } from "../hooks/usePaymentHistory";
import { useResumeSubscription } from "../hooks/useResumeSubscription";
import type {
  PaymentHistoryItem,
  PaymentStatus,
  RefundPaymentInfo,
} from "../types";
import { CancelSubscriptionFlow } from "./CancelSubscriptionFlow";
import { PaymentStatusBadge } from "./PaymentStatusBadge";
import { RefundRequestPopup } from "./RefundRequestPopup";
import { SubscriptionStatusCard } from "./SubscriptionStatusCard";

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

function formatPeriod(start: string | null, end: string | null): string {
  if (!start || !end) return "-";
  const s = new Date(start);
  const e = new Date(end);
  if (Number.isNaN(s.getTime()) || Number.isNaN(e.getTime())) return "-";
  const fmt = (d: Date) =>
    `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
      d.getDate()
    ).padStart(2, "0")}`;
  return `Pro · ${fmt(s)} ~ ${fmt(e)}`;
}

function formatAmount(amount: number): string {
  return `₩${amount.toLocaleString("ko-KR")}`;
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

export function PaymentHistoryTable() {
  const router = useRouter();
  const queryClient = useQueryClient();

  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = useState<PerPage>(20);
  const [isCancelOpen, setIsCancelOpen] = useState(false);
  const [refundTarget, setRefundTarget] = useState<RefundPaymentInfo | null>(
    null
  );

  const { data, isLoading, isError, refetch, isFetching } = usePaymentHistory(
    page,
    perPage
  );
  const { data: currentSub } = useCurrentSubscription();
  const { data: usage } = useUsageSummary();
  const resumeMutation = useResumeSubscription();

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = total === 0 ? 1 : Math.ceil(total / perPage);

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

  const handleResumeClick = useCallback(() => {
    if (resumeMutation.isPending) return;
    resumeMutation.mutate();
  }, [resumeMutation]);

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

  const handleCancelSuccess = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["billing", "current-subscription"] });
  }, [queryClient]);

  const showSubscribeButton = usage?.show_subscribe_button ?? false;

  return (
    <div className={styles.wrapper}>
      {currentSub?.status === "active" && (
        <SubscriptionStatusCard
          variant="active"
          nextChargeAt={currentSub.next_charge_at}
          onCancelClick={() => setIsCancelOpen(true)}
        />
      )}

      {currentSub?.status === "cancel_pending" && (
        <SubscriptionStatusCard
          variant="cancel_pending"
          effectiveAt={currentSub.current_period_end}
          onResumeClick={handleResumeClick}
          isResuming={resumeMutation.isPending}
        />
      )}

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
          <p className={styles.emptyTitle}>아직 결제 내역이 없어요.</p>
          <p className={styles.emptyBody}>
            Pro 구독으로 Denvia를 마음껏 활용해보세요.
          </p>
          {showSubscribeButton && (
            <button
              type="button"
              className={styles.subscribeBtn}
              onClick={() => router.push("/subscribe")}
            >
              구독 페이지로
            </button>
          )}
        </div>
      )}

      {!isLoading && !isError && total > 0 && (
        <>
          <div
            className={styles.tableScroll}
            aria-busy={isFetching ? "true" : "false"}
          >
            <table className={styles.table}>
              <caption className={styles.srOnly}>결제 내역</caption>
              <thead>
                <tr>
                  <th scope="col">결제일자</th>
                  <th scope="col">구독 상품 및 기간</th>
                  <th scope="col">구매자 이메일</th>
                  <th scope="col">결제수단</th>
                  <th scope="col" className={styles.amountCol}>
                    결제금액
                  </th>
                  <th scope="col">주문번호</th>
                  <th scope="col">결제상태</th>
                  <th scope="col" className={styles.actionCol}>
                    <span className={styles.srOnly}>액션</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.payment_id}>
                    <td data-label="결제일자">
                      {formatChargedAt(item.charged_at)}
                    </td>
                    <td data-label="구독 상품 및 기간">
                      {formatPeriod(
                        item.subscription_period_start,
                        item.subscription_period_end
                      )}
                    </td>
                    <td data-label="구매자 이메일" className={styles.emailCell}>
                      {item.buyer_email}
                    </td>
                    <td data-label="결제수단">
                      {formatCard(item.card_company, item.card_last4)}
                    </td>
                    <td data-label="결제금액" className={styles.amountCell}>
                      {formatAmount(item.amount_krw)}
                    </td>
                    <td
                      data-label="주문번호"
                      className={styles.orderIdCell}
                      title={item.provider_order_id}
                    >
                      {item.provider_order_id}
                    </td>
                    <td data-label="결제상태">
                      <PaymentStatusBadge status={item.status} />
                    </td>
                    <td className={styles.actionCell}>
                      {isRefundable(item.status) && (
                        <button
                          type="button"
                          className={styles.refundBtn}
                          onClick={() => handleRefundClick(item)}
                        >
                          환불 요청
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

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
        </>
      )}

      <CancelSubscriptionFlow
        isOpen={isCancelOpen}
        onClose={() => setIsCancelOpen(false)}
        currentPeriodEnd={currentSub?.current_period_end ?? null}
        onCancelSuccess={handleCancelSuccess}
      />

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
