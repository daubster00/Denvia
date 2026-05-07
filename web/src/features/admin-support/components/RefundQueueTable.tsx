"use client";

import { type KeyboardEvent, useMemo } from "react";
import type {
  RefundQueueItem,
  RefundQueueListResponse,
} from "@/features/admin-support/api/refunds";
import {
  REFUND_QUEUE_STATUS_LABELS,
  formatRefundReason,
} from "@/features/admin-support/labels";
import styles from "./RefundQueueTable.module.css";

interface Props {
  data: RefundQueueListResponse | undefined;
  isLoading: boolean;
  isError: boolean;
  page: number;
  perPage: number;
  onPageChange: (next: number) => void;
  onSelect: (item: RefundQueueItem) => void;
  onResetFilters: () => void;
  onRetry: () => void;
}

const KST_DATETIME = new Intl.DateTimeFormat("ko-KR", {
  timeZone: "Asia/Seoul",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

function formatDateTime(value: string | null): string {
  if (!value) return "—";
  try {
    return KST_DATETIME.format(new Date(value));
  } catch {
    return value;
  }
}

const KRW = new Intl.NumberFormat("ko-KR");

function badgeClassFor(status: RefundQueueItem["status"]): string {
  if (status === "approved") return styles.badgeApproved;
  if (status === "denied") return styles.badgeDenied;
  return styles.badgePending;
}

export function RefundQueueTable({
  data,
  isLoading,
  isError,
  page,
  perPage,
  onPageChange,
  onSelect,
  onResetFilters,
  onRetry,
}: Props) {
  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = useMemo(
    () => (total === 0 ? 1 : Math.ceil(total / perPage)),
    [total, perPage],
  );

  function handleRowKey(
    event: KeyboardEvent<HTMLTableRowElement>,
    item: RefundQueueItem,
  ) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onSelect(item);
    }
  }

  if (isError) {
    return (
      <div className={styles.errorBox} role="alert">
        <p className={styles.errorText}>환불 요청 목록을 불러오지 못했습니다.</p>
        <button type="button" className={styles.retryButton} onClick={onRetry}>
          다시 시도
        </button>
      </div>
    );
  }

  if (!isLoading && items.length === 0) {
    return (
      <div className={styles.emptyBox} role="status">
        <p className={styles.emptyTitle}>해당 조건의 환불 요청이 없습니다</p>
        <p className={styles.emptyHint}>상태나 기간 필터를 바꿔보세요.</p>
        <button
          type="button"
          className={styles.resetButton}
          onClick={onResetFilters}
        >
          필터 초기화
        </button>
      </div>
    );
  }

  return (
    <div className={styles.wrapper}>
      <table
        className={styles.table}
        role="table"
        aria-rowcount={total}
        aria-busy={isLoading}
      >
        <thead className={styles.thead}>
          <tr>
            <th scope="col">사용자</th>
            <th scope="col">금액</th>
            <th scope="col">카드</th>
            <th scope="col">사유</th>
            <th scope="col">경과일</th>
            <th scope="col">질의수</th>
            <th scope="col">상태</th>
            <th scope="col">요청일</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr
              key={item.queue_id}
              className={styles.row}
              role="row"
              tabIndex={0}
              onClick={() => onSelect(item)}
              onKeyDown={(e) => handleRowKey(e, item)}
              data-testid={`refund-row-${item.queue_id}`}
            >
              <td>{item.user_email_masked}</td>
              <td className={styles.amountCell}>
                {KRW.format(item.amount_krw)}원
              </td>
              <td>
                {item.card_company ?? "-"}{" "}
                {item.card_last4 ? `****${item.card_last4}` : ""}
              </td>
              <td className={styles.reasonCell}>{formatRefundReason(item.reason_code)}</td>
              <td>{item.days_since_charge}일</td>
              <td>{item.qa_count_during_period}건</td>
              <td>
                <span className={badgeClassFor(item.status)}>
                  {REFUND_QUEUE_STATUS_LABELS[item.status]}
                </span>
              </td>
              <td>{formatDateTime(item.requested_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <nav className={styles.pagination} aria-label="페이지 네비게이션">
        <button
          type="button"
          className={styles.pageButton}
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1 || isLoading}
          aria-label="이전 페이지"
        >
          이전
        </button>
        <span className={styles.pageLabel} aria-live="polite">
          {page} / {totalPages}
        </span>
        <button
          type="button"
          className={styles.pageButton}
          onClick={() => onPageChange(page + 1)}
          disabled={page >= totalPages || isLoading}
          aria-label="다음 페이지"
        >
          다음
        </button>
      </nav>
    </div>
  );
}
