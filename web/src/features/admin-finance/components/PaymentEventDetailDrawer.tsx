"use client";

import { useEffect, useRef } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  fetchPaymentEventDetail,
  type PaymentEventDetail,
  type PaymentEventType,
} from "@/features/admin-finance/api/payments";
import { getPaymentEventMeta } from "./PaymentDot";
import styles from "./PaymentEventDetailDrawer.module.css";

interface DrawerProps {
  eventId: number;
  onClose: () => void;
}

function fmtKstFull(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return `${d.toLocaleString("ko-KR", { timeZone: "Asia/Seoul", hour12: false })} (KST)`;
}

function fmtKrw(n: number): string {
  return `₩${n.toLocaleString("ko-KR")}`;
}

const STATUS_LABEL: Record<PaymentEventDetail["status"], string> = {
  pending: "결제 대기",
  success: "결제 완료",
  failed: "결제 실패",
  refunded: "환불 완료",
  refund_pending: "환불 진행 중",
};

const REFUND_EVENT_TYPES: ReadonlySet<PaymentEventType> = new Set([
  "refund_requested",
  "refund_success",
  "refund_denied",
]);

function isRefundEvent(t: PaymentEventType): boolean {
  return REFUND_EVENT_TYPES.has(t);
}

export function PaymentEventDetailDrawer({ eventId, onClose }: DrawerProps) {
  const dialogRef = useRef<HTMLDivElement | null>(null);

  const { data, error, isLoading } = useQuery({
    queryKey: ["admin", "finance", "payment-event-detail", eventId] as const,
    queryFn: () => fetchPaymentEventDetail(eventId),
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });

  // ESC 닫기
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  // Drawer 열릴 때 첫 포커스 가능 요소로 포커스 이동
  useEffect(() => {
    const node = dialogRef.current;
    if (!node) return;
    const firstFocusable = node.querySelector<HTMLElement>(
      'button, [href], input, [tabindex]:not([tabindex="-1"])',
    );
    firstFocusable?.focus();
  }, [eventId]);

  return (
    <div
      className={styles.backdrop}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      aria-hidden="false"
    >
      <aside
        ref={dialogRef}
        className={styles.drawer}
        role="dialog"
        aria-modal="true"
        aria-labelledby="payment-event-drawer-title"
      >
        <header className={styles.header}>
          <h2 id="payment-event-drawer-title" className={styles.title}>
            결제 이벤트 #{eventId}
          </h2>
          <button
            type="button"
            className={styles.closeBtn}
            aria-label="닫기"
            onClick={onClose}
          >
            ×
          </button>
        </header>

        {isLoading && (
          <p className={styles.stateMsg} role="status">불러오는 중…</p>
        )}
        {!isLoading && error && (
          <p className={styles.stateMsg} role="alert">
            {error instanceof Error && error.message === "EVENT_NOT_FOUND"
              ? "결제 이벤트를 찾을 수 없습니다."
              : "이벤트 정보를 불러오지 못했습니다."}
          </p>
        )}

        {data && (
          <>
            <dl className={styles.meta}>
              <dt>이벤트 시각</dt>
              <dd>{fmtKstFull(data.charged_at)}</dd>

              <dt>이벤트 종류</dt>
              <dd>{getPaymentEventMeta(data.event_type).label}</dd>

              <dt>결제 ID</dt>
              <dd>#{data.payment_id}</dd>

              <dt>결제 상태</dt>
              <dd>{STATUS_LABEL[data.status] ?? data.status}</dd>

              <dt>사용자</dt>
              <dd>
                {data.user_email_masked} (user #{data.user_id})
              </dd>

              <dt>카드</dt>
              <dd>
                {data.card_company || "—"}
                {data.card_last4 ? ` ****${data.card_last4}` : ""}
              </dd>

              <dt>금액</dt>
              <dd>{fmtKrw(data.amount_krw)}</dd>

              <dt>주문 ID</dt>
              <dd>
                <code className={styles.code}>{data.provider_order_id}</code>
              </dd>
            </dl>

            {data.provider_error_code && (
              <section className={styles.errorBox} aria-label="PG 에러 정보">
                <h3 className={styles.sectionHeading}>PG 에러</h3>
                <p>
                  <strong>코드: </strong>
                  <code className={styles.code}>{data.provider_error_code}</code>
                </p>
                {data.provider_error_message && (
                  <p className={styles.errorMessage}>
                    {data.provider_error_message}
                  </p>
                )}
              </section>
            )}

            {isRefundEvent(data.event_type) && data.refund_reason && (
              <section className={styles.refundBox} aria-label="환불 사유">
                <h3 className={styles.sectionHeading}>환불 사유</h3>
                <p className={styles.refundReason}>{data.refund_reason}</p>
              </section>
            )}

            <footer className={styles.actionBar}>
              {data.status === "success" && (
                <Link
                  href={`/admin/finance/payments/${data.payment_id}/refund`}
                  className={styles.actionLinkPrimary}
                >
                  이 결제 환불 처리
                </Link>
              )}
              <Link
                href={`/admin/users/${data.user_id}`}
                className={styles.actionLink}
              >
                사용자 보기
              </Link>
              <Link
                href={`/admin/finance/audit?target_type=payment&target_id=${data.payment_id}`}
                className={styles.actionLink}
              >
                감사 로그 보기
              </Link>
            </footer>
          </>
        )}
      </aside>
    </div>
  );
}
