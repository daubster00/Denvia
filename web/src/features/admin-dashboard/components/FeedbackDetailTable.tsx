"use client";

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
          📥 {isExporting ? "내보내는 중" : "엑셀 내보내기"}
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
          </colgroup>
          <thead>
            <tr>
              <th scope="col" className={styles.thQuestion}>질문</th>
              <th scope="col" className={styles.thAnswer}>답변</th>
              <th scope="col" className={styles.thRating}>피드백</th>
              <th scope="col" className={styles.thSegment}>가입유형</th>
              <th scope="col" className={styles.thDate}>제출일시</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 && (
              <tr>
                <td colSpan={5} className={styles.emptyRow} role="status">
                  이 기간에 피드백이 없습니다.
                </td>
              </tr>
            )}
            {items.map((item) => (
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
                <td className={styles.td}>{item.segment ?? "—"}</td>
                <td className={styles.td}>{formatKst(item.created_at)}</td>
              </tr>
            ))}
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
