"use client";

import { useEffect, useRef } from "react";
import type { AuditLogItem } from "@/features/admin-users/api/audit";
import {
  formatFinanceAuditAction,
  getFinanceAuditActionTone,
  parseFinanceAuditDiff,
} from "@/features/admin-finance/labels";
import styles from "./FinanceAuditDetailModal.module.css";

interface Props {
  open: boolean;
  log: AuditLogItem | undefined;
  onClose: () => void;
}

const KST_DATETIME = new Intl.DateTimeFormat("ko-KR", {
  timeZone: "Asia/Seoul",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
});

function formatDate(value: string): string {
  try {
    return KST_DATETIME.format(new Date(value));
  } catch {
    return value;
  }
}

function formatKrw(amount: number | null): string {
  if (amount === null) return "—";
  return `₩${amount.toLocaleString("ko-KR")}`;
}

function formatDuration(seconds: number | null): string {
  if (seconds === null) return "—";
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (hours > 0 && minutes > 0) return `${hours}시간 ${minutes}분`;
  if (hours > 0) return `${hours}시간`;
  return `${minutes}분`;
}

const TONE_CLASS: Record<string, string> = {
  approve: styles.actionApprove,
  deny: styles.actionDeny,
  extend: styles.actionExtend,
  generic: styles.actionGeneric,
};

export function FinanceAuditDetailModal({ open, log, onClose }: Props) {
  const drawerRef = useRef<HTMLDivElement>(null);
  const closeBtnRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    closeBtnRef.current?.focus();

    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open || !log) return null;

  const parsed = parseFinanceAuditDiff(log.action, log.diff_json);
  const tone = getFinanceAuditActionTone(log.action);
  const isSystem = log.actor_user_id === 0 || log.actor_user_id === null;

  return (
    <>
      <button
        type="button"
        aria-label="닫기"
        className={styles.overlay}
        onClick={onClose}
        tabIndex={-1}
      />
      <aside
        ref={drawerRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="finance-audit-detail-title"
        className={styles.drawer}
        data-testid="finance-audit-detail-modal"
      >
        <header className={styles.header}>
          <h2 id="finance-audit-detail-title" className={styles.title}>
            감사 로그 상세
          </h2>
          <button
            ref={closeBtnRef}
            type="button"
            onClick={onClose}
            aria-label="상세 닫기"
            className={styles.closeButton}
          >
            ×
          </button>
        </header>

        <section className={styles.section}>
          <h3 className={styles.sectionTitle}>액션</h3>
          <span
            className={`${styles.actionBadge} ${TONE_CLASS[tone] ?? styles.actionGeneric}`}
          >
            {formatFinanceAuditAction(log.action)}
          </span>
          <dl className={styles.metaList}>
            <dt>발생 시각</dt>
            <dd>{formatDate(log.created_at)}</dd>
            <dt>관리자</dt>
            <dd>
              {isSystem
                ? "시스템 자동"
                : log.actor_email ?? `(ID ${log.actor_user_id})`}
            </dd>
          </dl>
        </section>

        {(log.action === "refund.manual.approve" ||
          log.action === "refund.manual.deny") && (
          <section className={styles.section}>
            <h3 className={styles.sectionTitle}>환불 정보</h3>
            <dl className={styles.metaList}>
              <dt>금액</dt>
              <dd>{formatKrw(parsed.amountKrw)}</dd>
              <dt>결제 ID</dt>
              <dd>
                {parsed.paymentId !== null ? `#${parsed.paymentId}` : "—"}
              </dd>
              <dt>환불 큐 ID</dt>
              <dd>
                {log.target_id !== null ? `#${log.target_id}` : "—"}
              </dd>
              <dt>사유</dt>
              <dd>{parsed.reasonLabel ?? "—"}</dd>
              {parsed.noteLength !== null && (
                <>
                  <dt>관리자 메모</dt>
                  <dd>{parsed.noteLength}자</dd>
                </>
              )}
            </dl>
          </section>
        )}

        {log.action === "subscription.extended_killswitch" && (
          <section className={styles.section}>
            <h3 className={styles.sectionTitle}>자동 연장 정보</h3>
            <dl className={styles.metaList}>
              <dt>연장 시간</dt>
              <dd>{formatDuration(parsed.durationSeconds)}</dd>
              <dt>연장 후 만료</dt>
              <dd>
                {parsed.extendedTo
                  ? formatDate(parsed.extendedTo)
                  : "—"}
              </dd>
              <dt>구독 ID</dt>
              <dd>
                {log.target_id !== null ? `#${log.target_id}` : "—"}
              </dd>
              <dt>비상정지 상태 ID</dt>
              <dd>
                {parsed.killswitchStateId !== null
                  ? `#${parsed.killswitchStateId}`
                  : "—"}
              </dd>
            </dl>
          </section>
        )}

        <section className={styles.section}>
          <h3 className={styles.sectionTitle}>기술 메타</h3>
          <dl className={styles.metaList}>
            <dt>IP</dt>
            <dd className={styles.mono}>{log.ip ?? "—"}</dd>
            <dt>Trace ID</dt>
            <dd className={styles.mono}>{log.trace_id ?? "—"}</dd>
            <dt>User-Agent</dt>
            <dd className={styles.uaText}>{log.ua ?? "—"}</dd>
          </dl>
        </section>
      </aside>
    </>
  );
}
