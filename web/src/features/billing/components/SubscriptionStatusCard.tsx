"use client";

/** SubscriptionStatusCard — 현재 구독 상태 표시 (active / cancel_pending). Story 3.5. */

import styles from "./SubscriptionStatusCard.module.css";

function formatKoreanDate(iso: string | null | undefined): string {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "-";
  return `${d.getFullYear()}년 ${String(d.getMonth() + 1).padStart(2, "0")}월 ${String(
    d.getDate()
  ).padStart(2, "0")}일`;
}

interface ActiveProps {
  variant: "active";
  nextChargeAt: string | null;
  onCancelClick: () => void;
}

interface CancelPendingProps {
  variant: "cancel_pending";
  effectiveAt: string | null;
  onResumeClick: () => void;
  isResuming?: boolean;
}

export type SubscriptionStatusCardProps = ActiveProps | CancelPendingProps;

export function SubscriptionStatusCard(props: SubscriptionStatusCardProps) {
  if (props.variant === "active") {
    return (
      <div className={styles.card}>
        <div className={styles.info}>
          <p className={styles.heading}>현재 Pro 구독 중</p>
          <p className={styles.subtitle}>
            다음 결제일: {formatKoreanDate(props.nextChargeAt)}
          </p>
        </div>
        <button
          type="button"
          className={styles.dangerBtn}
          onClick={props.onCancelClick}
        >
          구독 해지
        </button>
      </div>
    );
  }

  return (
    <div className={`${styles.card} ${styles.cardCancelPending}`}>
      <div className={styles.info}>
        <p className={`${styles.heading} ${styles.headingPending}`}>
          해지 예정 ({formatKoreanDate(props.effectiveAt)} 적용)
        </p>
        <p className={`${styles.subtitle} ${styles.subtitlePending}`}>
          적용 전까지 Pro 혜택을 그대로 이용하실 수 있습니다.
        </p>
      </div>
      <button
        type="button"
        className={styles.secondaryBtn}
        onClick={props.onResumeClick}
        disabled={props.isResuming}
      >
        해지 철회
      </button>
    </div>
  );
}
