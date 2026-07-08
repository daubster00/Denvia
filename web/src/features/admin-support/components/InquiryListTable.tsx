"use client";

import { type KeyboardEvent, useMemo } from "react";
import type {
  InquiryListItem,
  InquiryListResponse,
} from "@/features/admin-support/api/inquiries";
import {
  formatInquiryStatus,
  formatInquiryType,
  formatSegment,
} from "@/features/admin-support/labels";
import styles from "./InquiryListTable.module.css";

interface Props {
  data: InquiryListResponse | undefined;
  isLoading: boolean;
  isError: boolean;
  page: number;
  perPage: number;
  onPageChange: (next: number) => void;
  onSelect: (item: InquiryListItem) => void;
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

function badgeClassFor(status: string): string {
  if (status === "resolved") return styles.badgeResolved;
  if (status === "in_progress") return styles.badgeProgress;
  return styles.badgeOpen;
}

export function InquiryListTable({
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
    item: InquiryListItem,
  ) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onSelect(item);
    }
  }

  if (isError) {
    return (
      <div className={styles.errorBox} role="alert">
        <p className={styles.errorText}>문의 목록을 불러오지 못했습니다.</p>
        <button type="button" className={styles.retryButton} onClick={onRetry}>
          다시 시도
        </button>
      </div>
    );
  }

  if (!isLoading && items.length === 0) {
    return (
      <div className={styles.emptyBox} role="status">
        <p className={styles.emptyTitle}>해당 조건의 문의가 없습니다</p>
        <p className={styles.emptyHint}>상태 또는 검색어를 바꿔보세요.</p>
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
      <div className={styles.tableScroll}>
      <table
        className={styles.table}
        role="table"
        aria-rowcount={total}
        aria-busy={isLoading}
      >
        <thead className={styles.thead}>
          <tr>
            <th scope="col">제목</th>
            <th scope="col">유형</th>
            <th scope="col">사용자</th>
            <th scope="col">가입유형</th>
            <th scope="col">상태</th>
            <th scope="col">접수일</th>
            <th scope="col">완료일</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr
              key={item.id}
              className={styles.row}
              role="row"
              tabIndex={0}
              onClick={() => onSelect(item)}
              onKeyDown={(e) => handleRowKey(e, item)}
              data-testid={`inquiry-row-${item.id}`}
            >
              <td className={styles.subjectCell}>
                <div className={styles.subjectLine}>{item.subject}</div>
                {item.body_preview ? (
                  <div className={styles.preview}>{item.body_preview}</div>
                ) : null}
              </td>
              <td>{formatInquiryType(item.inquiry_type)}</td>
              <td>{item.user_email}</td>
              <td>{formatSegment(item.segment)}</td>
              <td>
                <span className={badgeClassFor(item.status)}>
                  {formatInquiryStatus(item.status)}
                </span>
              </td>
              <td>{formatDateTime(item.created_at)}</td>
              <td>{formatDateTime(item.resolved_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>

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
