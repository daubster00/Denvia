"use client";

import type { QaReviewItem } from "../api";
import styles from "./QaReviewRow.module.css";

interface Props {
  item: QaReviewItem;
  /** master/operator 권한 여부. false(부운영자)면 체크박스·사용자정보를 감춘다. */
  privileged: boolean;
  selected: boolean;
  onToggleSelect: (qaLogId: number, next: boolean) => void;
  /** 검토/수정 버튼 클릭 → 상세/평가 모달 열기. */
  onOpen: (item: QaReviewItem) => void;
}

function formatDateTime(iso: string | null): string {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  const hh = String(d.getHours()).padStart(2, "0");
  const mi = String(d.getMinutes()).padStart(2, "0");
  return `${d.getFullYear()}-${mm}-${dd} ${hh}:${mi}`;
}

export function QaReviewRow({
  item,
  privileged,
  selected,
  onToggleSelect,
  onOpen,
}: Props) {
  const review = item.review;
  const isReviewed = review.reviewed_at != null;

  // 평가 결과 — 굿/배드, 평가 안 했으면 그냥 "-".
  const ratingCell =
    review.rating === "good" ? (
      <span className={styles.badgeGood}>굿</span>
    ) : review.rating === "bad" ? (
      <span className={styles.badgeBad}>배드</span>
    ) : (
      <span className={styles.ratingNone}>-</span>
    );

  return (
    <tr className={styles.row}>
      {privileged && (
        <td className={styles.checkCell}>
          <input
            type="checkbox"
            checked={selected}
            onChange={(e) => onToggleSelect(item.qa_log_id, e.target.checked)}
            aria-label="이 행 선택"
          />
        </td>
      )}

      <td className={styles.textCell}>
        <div className={styles.question}>{item.question}</div>
        <div className={styles.meta}>{formatDateTime(item.created_at)}</div>
      </td>

      <td className={styles.answerCell}>
        <div className={styles.answer}>
          {item.answer && item.answer.trim() ? item.answer : "답변 없음"}
        </div>
      </td>

      <td className={styles.ratingCell}>{ratingCell}</td>

      <td className={styles.statusCell}>
        {isReviewed ? (
          <span className={styles.statusReviewed}>검토완료</span>
        ) : (
          <span className={styles.statusPending}>검토전</span>
        )}
      </td>

      {privileged && (
        <td className={styles.userCell}>
          {item.user ? item.user.email ?? item.user.segment ?? "-" : "-"}
        </td>
      )}

      <td className={styles.actionCell}>
        <button
          type="button"
          className={isReviewed ? styles.editBtn : styles.reviewBtn}
          onClick={() => onOpen(item)}
        >
          {isReviewed ? "수정" : "검토"}
        </button>
      </td>
    </tr>
  );
}
