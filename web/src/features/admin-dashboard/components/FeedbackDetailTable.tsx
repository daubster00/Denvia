"use client";

import Link from "next/link";
import { IconDownload } from "@wanteddev/wds-icon";
import type { FeedbackItem } from "../api/analytics";
import styles from "./FeedbackDetailTable.module.css";

interface FeedbackDetailTableProps {
  items: FeedbackItem[];
  total: number;
  page: number;
  perPage: number;
  onPageChange: (page: number) => void;
  onRowClick: (item: FeedbackItem) => void;
  onExport: () => void;
  onToggleReviewed: (item: FeedbackItem) => void;
  pendingReviewIds?: Set<number>;
  isExporting?: boolean;
  exportError?: string | null;
}

export function FeedbackDetailTable({
  items,
  total,
  page,
  perPage,
  onPageChange,
  onRowClick,
  onExport,
  onToggleReviewed,
  pendingReviewIds,
  isExporting = false,
  exportError = null,
}: FeedbackDetailTableProps) {
  const totalPages = Math.max(1, Math.ceil(total / perPage));

  return (
    <div className={styles.wrapper}>
      <div className={styles.tableActions}>
        <p className={styles.totalCount}>전체 {total.toLocaleString()}건</p>
        <button
          type="button"
          className={styles.exportBtn}
          onClick={onExport}
          aria-label="현재 필터 기준으로 엑셀 내보내기"
          disabled={isExporting}
        >
          <IconDownload aria-hidden="true" />
          <span>{isExporting ? "내보내는 중" : "엑셀 내보내기"}</span>
        </button>
      </div>
      {exportError && (
        <p className={styles.exportError} role="alert">
          {exportError}
        </p>
      )}

      <div className={styles.tableScroll}>
        <table className={styles.table}>
          <colgroup>
            <col className={styles.colQuestion} />
            <col className={styles.colAnswer} />
            <col className={styles.colRating} />
            <col className={styles.colSegment} />
            <col className={styles.colDate} />
            <col className={styles.colReviewStatus} />
            <col className={styles.colReviewAction} />
          </colgroup>
          <thead>
            <tr>
              <th scope="col" className={styles.thQuestion}>질문</th>
              <th scope="col" className={styles.thAnswer}>답변</th>
              <th scope="col" className={styles.thRating}>피드백</th>
              <th scope="col" className={styles.thSegment}>계정</th>
              <th scope="col" className={styles.thDate}>제출일시</th>
              <th scope="col" className={styles.thReviewStatus}>검토 상태</th>
              <th scope="col" className={styles.thReviewAction}>검토 작업</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 && (
              <tr>
                <td colSpan={7} className={styles.emptyRow} role="status">
                  이 기간에 피드백이 없습니다.
                </td>
              </tr>
            )}
            {items.map((item) => {
              const reviewed = item.reviewed_at != null;
              const pending = pendingReviewIds?.has(item.qa_log_id) ?? false;
              return (
                <tr
                  key={item.qa_log_id}
                  className={styles.row}
                  onClick={() => onRowClick(item)}
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") onRowClick(item);
                  }}
                  aria-label="피드백 상세 보기"
                >
                  <td className={styles.td}>
                    <span className={styles.tdClamp}>{item.question_text}</span>
                  </td>
                  <td className={styles.td}>
                    <span className={styles.tdClamp}>{item.answer_text ?? "—"}</span>
                  </td>
                  <td className={styles.td}>
                    <span
                      className={
                        item.rating === "good"
                          ? styles.badgeGood
                          : styles.badgeBad
                      }
                    >
                      {item.rating === "good" ? "👍 GOOD" : "👎 BAD"}
                    </span>
                  </td>
                  <td className={styles.td}>
                    {item.user_id !== null && item.email ? (
                      <Link
                        href={`/admin/users/${item.user_id}`}
                        className={styles.accountLink}
                        onClick={(e) => e.stopPropagation()}
                        title={`${item.email} 고객 관리 페이지로 이동`}
                      >
                        {item.email}
                      </Link>
                    ) : (
                      <span className={styles.accountAnon}>비회원</span>
                    )}
                  </td>
                  <td className={styles.td}>{formatKst(item.created_at)}</td>
                  <td className={styles.td}>
                    <span
                      className={
                        reviewed
                          ? styles.statusReviewed
                          : styles.statusPending
                      }
                    >
                      {reviewed ? "✓ 검토완료" : "미검토"}
                    </span>
                  </td>
                  <td className={styles.td}>
                    <button
                      type="button"
                      className={
                        reviewed ? styles.reviewBtnUndo : styles.reviewBtn
                      }
                      onClick={(e) => {
                        e.stopPropagation();
                        onToggleReviewed(item);
                      }}
                      disabled={pending}
                      aria-pressed={reviewed}
                      title={
                        reviewed
                          ? "검토완료 해제 (미검토로 되돌리기)"
                          : "이 피드백을 검토완료로 표시"
                      }
                    >
                      {pending
                        ? "처리 중…"
                        : reviewed
                          ? "되돌리기"
                          : "검토완료"}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className={styles.pagination}>
        <button
          type="button"
          className={styles.pageBtn}
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
          aria-label="이전 페이지"
        >
          이전
        </button>
        <span className={styles.pageInfo}>
          {page} / {totalPages}
        </span>
        <button
          type="button"
          className={styles.pageBtn}
          disabled={page >= totalPages}
          onClick={() => onPageChange(page + 1)}
          aria-label="다음 페이지"
        >
          다음
        </button>
      </div>
    </div>
  );
}

function formatKst(iso: string): string {
  try {
    const d = new Date(iso);
    return new Intl.DateTimeFormat("ko-KR", {
      timeZone: "Asia/Seoul",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(d);
  } catch {
    return iso;
  }
}
