"use client";

/** PaymentStatusBadge — 결제 상태 5종 한글 라벨 + 색상 뱃지 (Story 4.4 / UX-DR24). */

import type { PaymentStatus } from "../types";
import styles from "./PaymentStatusBadge.module.css";

const LABELS: Record<PaymentStatus, string> = {
  pending: "처리 중",
  success: "결제 완료",
  failed: "실패",
  refunded: "환불 완료",
  refund_pending: "환불 처리 중",
};

export function PaymentStatusBadge({ status }: { status: PaymentStatus }) {
  return (
    <span
      className={`${styles.badge} ${styles[status]}`}
      aria-label={`결제 상태: ${LABELS[status]}`}
    >
      {LABELS[status]}
    </span>
  );
}
