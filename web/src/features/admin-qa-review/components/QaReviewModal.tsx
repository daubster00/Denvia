"use client";

import { useEffect, useRef, useState } from "react";
import type { QaRating, QaReviewItem } from "../api";
import styles from "./QaReviewModal.module.css";

interface Props {
  item: QaReviewItem;
  /** master/operator 권한 여부. false(부운영자)면 검토완료·사용자정보를 감춘다. */
  privileged: boolean;
  onClose: () => void;
  /** 평가(굿/배드/해제) + 메모를 한 번에 저장. 실패 시 throw. */
  onSave: (
    item: QaReviewItem,
    rating: QaRating | null,
    comment: string,
  ) => Promise<void>;
  onToggleComplete: (item: QaReviewItem) => Promise<void>;
  completePending: boolean;
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

export function QaReviewModal({
  item,
  privileged,
  onClose,
  onSave,
  onToggleComplete,
  completePending,
}: Props) {
  const review = item.review;
  const isReviewed = review.reviewed_at != null;
  const hasMemo = !!(review.comment && review.comment.trim());

  // 서버 값 기준 초안 상태 — '평가수정' 없이 항상 편집 가능. 열려 있는 동안 다른
  // 항목으로 바뀌면(리스트 갱신·저장 반영) 초안을 서버 값으로 다시 동기화한다.
  const [draftRating, setDraftRating] = useState<QaRating | null>(review.rating);
  const [draftComment, setDraftComment] = useState(review.comment ?? "");
  const [syncKey, setSyncKey] = useState(
    `${review.rating ?? ""}|${review.comment ?? ""}`,
  );
  const serverKey = `${review.rating ?? ""}|${review.comment ?? ""}`;
  if (serverKey !== syncKey) {
    setSyncKey(serverKey);
    setDraftRating(review.rating);
    setDraftComment(review.comment ?? "");
  }

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mouseDownOnOverlayRef = useRef(false);

  useEffect(() => {
    const handle = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handle);
    return () => document.removeEventListener("keydown", handle);
  }, [onClose]);

  const dirty =
    draftRating !== review.rating ||
    draftComment.trim() !== (review.comment ?? "").trim();

  // '저장' — 평가(굿/배드/해제) + 메모를 저장한다. 성공 시 서버 값이 캐시에 반영되며
  // 위 동기화 로직이 초안을 새 값으로 맞추고, 작성자 계정·작성일자가 갱신된다.
  const handleSave = async () => {
    setError(null);
    setSaving(true);
    try {
      await onSave(item, draftRating, draftComment.trim());
    } catch {
      setError("저장에 실패했습니다. 잠시 후 다시 시도해 주세요.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      role="presentation"
      className={styles.overlay}
      onMouseDown={(e) => {
        mouseDownOnOverlayRef.current = e.target === e.currentTarget;
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget && mouseDownOnOverlayRef.current) {
          onClose();
        }
        mouseDownOnOverlayRef.current = false;
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="질의응답 검토"
        className={styles.dialog}
      >
        <div className={styles.header}>
          <h2 className={styles.title}>질의응답 검토</h2>
          <button
            type="button"
            onClick={onClose}
            className={styles.closeBtn}
            aria-label="닫기"
          >
            ✕
          </button>
        </div>

        <div className={styles.body}>
          <div className={styles.field}>
            <span className={styles.fieldLabel}>질문</span>
            <p className={styles.question}>{item.question}</p>
            <span className={styles.meta}>{formatDateTime(item.created_at)}</span>
          </div>

          <div className={styles.field}>
            <span className={styles.fieldLabel}>답변</span>
            <p className={styles.answer}>{item.answer ?? "-"}</p>
          </div>

          {privileged && item.user && (
            <div className={styles.field}>
              <span className={styles.fieldLabel}>사용자</span>
              <p className={styles.userLine}>
                {item.user.email ?? item.user.segment ?? "-"}
              </p>
            </div>
          )}

          <div className={styles.field}>
            <span className={styles.fieldLabel}>평가</span>
            <div className={styles.rateBtns}>
              <button
                type="button"
                className={
                  draftRating === "good" ? styles.goodBtnActive : styles.goodBtn
                }
                aria-pressed={draftRating === "good"}
                disabled={saving}
                onClick={() =>
                  setDraftRating((prev) => (prev === "good" ? null : "good"))
                }
              >
                굿
              </button>
              <button
                type="button"
                className={
                  draftRating === "bad" ? styles.badBtnActive : styles.badBtn
                }
                aria-pressed={draftRating === "bad"}
                disabled={saving}
                onClick={() =>
                  setDraftRating((prev) => (prev === "bad" ? null : "bad"))
                }
              >
                배드
              </button>
              {draftRating === null && (
                <span className={styles.unratedHint}>선택 안 함(미평가)</span>
              )}
            </div>
          </div>

          <div className={styles.field}>
            <label className={styles.fieldLabel} htmlFor="qa-review-memo">
              평가 메모
            </label>
            {/* '평가수정'/'평가하기' 없이 항상 입력 가능. 단 메모는 굿/배드를
                먼저 선택해야 작성할 수 있다(백엔드 규칙과 동일). */}
            <textarea
              id="qa-review-memo"
              className={styles.memoInput}
              value={draftComment}
              onChange={(e) => setDraftComment(e.target.value)}
              placeholder={
                draftRating === null
                  ? "먼저 굿 또는 배드를 선택한 뒤 메모를 남길 수 있습니다."
                  : "평가 사유·개선점 등을 자유롭게 적어주세요."
              }
              rows={4}
              maxLength={2000}
              disabled={saving || draftRating === null}
            />
            {/* 마지막으로 저장된 메모의 작성자 계정(좌) + 작성일자(우측 끝). */}
            {hasMemo && review.rated_by_name && (
              <div className={styles.memoMetaRow}>
                <span className={styles.memoAuthor}>
                  작성자 {review.rated_by_name}
                </span>
                {review.rated_at && (
                  <span className={styles.memoDate}>
                    {formatDateTime(review.rated_at)}
                  </span>
                )}
              </div>
            )}
            <div className={styles.memoEditActions}>
              <button
                type="button"
                className={styles.memoDoneBtn}
                onClick={handleSave}
                disabled={saving || !dirty}
              >
                {saving ? "저장 중…" : "저장"}
              </button>
            </div>
          </div>

          {privileged && review.change_count > 0 && (
            <p className={styles.changeCount}>수정 {review.change_count}회</p>
          )}
        </div>

        {error && (
          <p className={styles.errorMsg} role="alert">
            {error}
          </p>
        )}

        <div className={styles.actions}>
          {privileged && (
            <button
              type="button"
              className={isReviewed ? styles.reviewedBtn : styles.reviewBtn}
              disabled={completePending}
              onClick={() => onToggleComplete(item)}
            >
              {isReviewed
                ? review.reviewed_by_name
                  ? `검토완료됨 · ${review.reviewed_by_name}`
                  : "검토완료됨"
                : "검토완료로 표시"}
            </button>
          )}
          <div className={styles.actionsRight}>
            <button type="button" onClick={onClose} className={styles.cancelBtn}>
              닫기
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
