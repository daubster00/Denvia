"use client";

import type { PaymentEventType } from "@/features/admin-finance/api/payments";
import styles from "./PaymentDot.module.css";

export interface PaymentEventMeta {
  label: string;
  toneClass: string;
}

const META: Record<PaymentEventType, PaymentEventMeta> = {
  charge_requested: { label: "결제 요청", toneClass: "neutral" },
  charge_success: { label: "결제 완료", toneClass: "success" },
  charge_failed: { label: "결제 실패", toneClass: "chargeFailed" },
  retry_scheduled: { label: "재시도 예약", toneClass: "warning" },
  refund_requested: { label: "환불 요청", toneClass: "refundPending" },
  refund_success: { label: "환불 완료", toneClass: "refunded" },
  refund_denied: { label: "환불 거절", toneClass: "failed" },
};

export function getPaymentEventMeta(type: PaymentEventType): PaymentEventMeta {
  return META[type];
}

interface PaymentDotProps {
  type: PaymentEventType;
  /** 도트만 단독 노출 시 시각 보조 라벨로 부착 */
  ariaLabel?: string;
}

export function PaymentDot({ type, ariaLabel }: PaymentDotProps) {
  const meta = META[type];
  return (
    <span
      className={`${styles.dot} ${styles[meta.toneClass]}`}
      role="img"
      aria-label={ariaLabel ?? meta.label}
    />
  );
}
