"use client";

import { useEffect, useRef } from "react";
import type { AuditLogItem } from "@/features/admin-users/api/audit";
import {
  formatAuditAction,
  formatDiffField,
  formatDiffValue,
} from "@/features/admin-users/labels";
import styles from "./AuditDiffDrawer.module.css";

interface Props {
  open: boolean;
  log: AuditLogItem | undefined;
  onClose: () => void;
}

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"]), input, select, textarea';

const KST_DATETIME = new Intl.DateTimeFormat("ko-KR", {
  timeZone: "Asia/Seoul",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

function formatDate(value: string): string {
  try {
    return KST_DATETIME.format(new Date(value));
  } catch {
    return value;
  }
}

interface DiffEntry {
  field: string;
  before: unknown;
  after: unknown;
  status: "added" | "removed" | "changed";
}

function buildDiffEntries(
  before: Record<string, unknown>,
  after: Record<string, unknown>,
): DiffEntry[] {
  const keys = Array.from(
    new Set([...Object.keys(before), ...Object.keys(after)]),
  );
  return keys.map((field) => {
    const inBefore = field in before;
    const inAfter = field in after;
    if (!inBefore) {
      return {
        field,
        before: undefined,
        after: after[field],
        status: "added" as const,
      };
    }
    if (!inAfter) {
      return {
        field,
        before: before[field],
        after: undefined,
        status: "removed" as const,
      };
    }
    return {
      field,
      before: before[field],
      after: after[field],
      status: "changed" as const,
    };
  });
}

export function AuditDiffDrawer({ open, log, onClose }: Props) {
  const drawerRef = useRef<HTMLDivElement>(null);
  const closeBtnRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    closeBtnRef.current?.focus();

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        onClose();
        return;
      }
      if (e.key === "Tab" && drawerRef.current) {
        const focusable = drawerRef.current.querySelectorAll<HTMLElement>(
          FOCUSABLE_SELECTOR,
        );
        if (focusable.length === 0) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  if (!open || !log) return null;

  const diff = log.diff_json ?? {};
  const before = ((diff as Record<string, unknown>).before ?? {}) as Record<
    string,
    unknown
  >;
  const after = ((diff as Record<string, unknown>).after ?? {}) as Record<
    string,
    unknown
  >;
  const metadata = ((diff as Record<string, unknown>).metadata ?? null) as
    | Record<string, unknown>
    | null;

  const entries = buildDiffEntries(before, after);
  const isSystem = log.action === "user.block_auto_expired";

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
        aria-labelledby="audit-diff-title"
        className={styles.drawer}
        data-testid="audit-diff-drawer"
      >
        <header className={styles.header}>
          <h2 id="audit-diff-title" className={styles.title}>
            수정 이력 상세
          </h2>
          <button
            ref={closeBtnRef}
            type="button"
            onClick={onClose}
            aria-label="Drawer 닫기"
            className={styles.closeButton}
          >
            ✕
          </button>
        </header>

        <section className={styles.section}>
          <h3 className={styles.sectionTitle}>액션</h3>
          <p className={styles.actionRow}>
            <span className={styles.actionLabel}>
              {formatAuditAction(log.action)}
            </span>
            <span className={styles.timestamp}>
              {formatDate(log.created_at)}
            </span>
          </p>
        </section>

        <section className={styles.section}>
          <h3 className={styles.sectionTitle}>대상</h3>
          <p className={styles.targetText}>
            {log.target_email ?? "—"}{" "}
            {log.target_id !== null ? `(ID ${log.target_id})` : ""}
          </p>
          <p className={styles.actorText}>
            관리자:{" "}
            {isSystem
              ? "시스템 자동"
              : log.actor_email ?? `(ID ${log.actor_user_id})`}
          </p>
        </section>

        <section className={styles.section}>
          <h3 className={styles.sectionTitle}>변경 내역</h3>
          {entries.length === 0 ? (
            <p className={styles.placeholder}>변경 필드 없음</p>
          ) : (
            <dl className={styles.diffList}>
              {entries.map((entry) => (
                <div
                  key={entry.field}
                  className={
                    entry.status === "added"
                      ? styles.diffAdded
                      : entry.status === "removed"
                        ? styles.diffRemoved
                        : styles.diffChanged
                  }
                  data-testid={`diff-row-${entry.field}`}
                >
                  <dt>
                    <span className={styles.marker} aria-hidden="true">
                      {entry.status === "added"
                        ? "+"
                        : entry.status === "removed"
                          ? "−"
                          : "Δ"}
                    </span>
                    {formatDiffField(entry.field)}
                  </dt>
                  <dd>
                    {entry.status === "changed" ? (
                      <>
                        <span className={styles.beforeVal}>
                          {formatDiffValue(entry.field, entry.before)}
                        </span>
                        <span className={styles.arrow}>→</span>
                        <span className={styles.afterVal}>
                          {formatDiffValue(entry.field, entry.after)}
                        </span>
                      </>
                    ) : entry.status === "added" ? (
                      <span className={styles.afterVal}>
                        {formatDiffValue(entry.field, entry.after)}
                      </span>
                    ) : (
                      <span className={styles.beforeVal}>
                        {formatDiffValue(entry.field, entry.before)}
                      </span>
                    )}
                  </dd>
                </div>
              ))}
            </dl>
          )}
        </section>

        {metadata ? (
          <section className={styles.section}>
            <h3 className={styles.sectionTitle}>추가 정보</h3>
            <dl className={styles.metaList}>
              {Object.entries(metadata).map(([key, value]) => (
                <div key={key} className={styles.metaRow}>
                  <dt>{formatDiffField(key)}</dt>
                  <dd>{formatDiffValue(key, value)}</dd>
                </div>
              ))}
            </dl>
          </section>
        ) : null}

        <section className={styles.section}>
          <h3 className={styles.sectionTitle}>기술 메타</h3>
          <dl className={styles.metaList}>
            <div className={styles.metaRow}>
              <dt>IP</dt>
              <dd className={styles.mono}>{log.ip ?? "—"}</dd>
            </div>
            <div className={styles.metaRow}>
              <dt>Trace ID</dt>
              <dd className={styles.mono}>{log.trace_id ?? "—"}</dd>
            </div>
            <div className={styles.metaRow}>
              <dt>User-Agent</dt>
              <dd className={styles.uaText}>{log.ua ?? "—"}</dd>
            </div>
          </dl>
        </section>
      </aside>
    </>
  );
}
