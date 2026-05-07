"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  fetchPaymentEventDetail,
  type PaymentEventDetail,
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

export function PaymentEventDetailDrawer({ eventId, onClose }: DrawerProps) {
  const [copyToast, setCopyToast] = useState<string | null>(null);
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

  const handleCopy = async () => {
    if (!data?.raw_response_json) return;
    try {
      await navigator.clipboard.writeText(
        JSON.stringify(data.raw_response_json, null, 2),
      );
      setCopyToast("복사됨");
      window.setTimeout(() => setCopyToast(null), 2000);
    } catch {
      setCopyToast("복사 실패");
      window.setTimeout(() => setCopyToast(null), 2000);
    }
  };

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

            <section className={styles.jsonSection} aria-label="PG 응답 원본 JSON">
              <h3 className={styles.sectionHeading}>PG 응답 원본 (raw_response_json)</h3>
              <pre className={styles.jsonViewer}>
                <code>
                  {data.raw_response_json
                    ? JSON.stringify(data.raw_response_json, null, 2)
                    : "(no response payload)"}
                </code>
              </pre>
            </section>

            <footer className={styles.actionBar}>
              <button
                type="button"
                className={styles.actionBtn}
                onClick={handleCopy}
                disabled={!data.raw_response_json}
              >
                JSON 복사
              </button>
              <Link
                href={`/admin/users/${data.user_id}`}
                className={styles.actionLink}
              >
                사용자 보기
              </Link>
              <span
                className={styles.actionLinkDisabled}
                title="Story 9.3에서 활성화"
              >
                환불 검토 큐로 (준비 중)
              </span>
              <Link
                href={`/admin/users/edits?target_id=${data.payment_id}&action_in=billing.refund`}
                className={styles.actionLink}
              >
                감사 로그 보기
              </Link>
              {copyToast && (
                <span className={styles.toast} role="status">
                  {copyToast}
                </span>
              )}
            </footer>
          </>
        )}
      </aside>
    </div>
  );
}
