"use client";

import { useMemo, type KeyboardEvent } from "react";
import type { PaymentEventItem } from "@/features/admin-finance/api/payments";
import { getPaymentEventMeta, PaymentDot } from "./PaymentDot";
import styles from "./AdminLogTimeline.module.css";

interface AdminLogTimelineProps {
  events: PaymentEventItem[];
  onRowClick: (event: PaymentEventItem) => void;
  groupByDate?: boolean;
  isLoading?: boolean;
  emptyMessage?: string;
}

function toKstDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  // Asia/Seoul 명시 — 사용자 OS 타임존 영향 차단
  return d.toLocaleDateString("ko-KR", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
}

function toKstTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleTimeString("ko-KR", {
    timeZone: "Asia/Seoul",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function formatKrw(n: number): string {
  return `₩${n.toLocaleString("ko-KR")}`;
}

function groupEventsByDate(
  events: PaymentEventItem[],
): Array<[string, PaymentEventItem[]]> {
  const map = new Map<string, PaymentEventItem[]>();
  for (const e of events) {
    const key = toKstDate(e.charged_at);
    const arr = map.get(key) ?? [];
    arr.push(e);
    map.set(key, arr);
  }
  return Array.from(map.entries());
}

export function AdminLogTimeline({
  events,
  onRowClick,
  groupByDate = true,
  isLoading = false,
  emptyMessage = "조회된 결제 이벤트가 없습니다.",
}: AdminLogTimelineProps) {
  const groups = useMemo(
    () => (groupByDate ? groupEventsByDate(events) : [["", events]] as Array<[string, PaymentEventItem[]]>),
    [events, groupByDate],
  );

  if (isLoading) {
    return (
      <p className={styles.stateMsg} role="status">
        결제 이벤트를 불러오는 중…
      </p>
    );
  }

  if (events.length === 0) {
    return (
      <p className={styles.stateMsg} role="status">
        {emptyMessage}
      </p>
    );
  }

  const handleKeyDown = (
    e: KeyboardEvent<HTMLLIElement>,
    item: PaymentEventItem,
  ) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onRowClick(item);
    }
  };

  return (
    <ol className={styles.timeline} aria-label="결제 이벤트 타임라인">
      {groups.map(([dateLabel, items]) => (
        <li key={dateLabel || "all"} className={styles.group}>
          {groupByDate && dateLabel && (
            <h3 className={styles.dateHeading}>{dateLabel}</h3>
          )}
          <ul className={styles.rows}>
            {items.map((it) => {
              const meta = getPaymentEventMeta(it.event_type);
              return (
                <li
                  key={it.event_id}
                  tabIndex={0}
                  role="button"
                  aria-label={`결제 이벤트 #${it.event_id} 상세 보기 — ${meta.label} ${formatKrw(it.amount_krw)} ${it.user_email_masked}`}
                  className={styles.row}
                  onClick={() => onRowClick(it)}
                  onKeyDown={(e) => handleKeyDown(e, it)}
                >
                  <span className={styles.dotCell}>
                    <PaymentDot type={it.event_type} />
                  </span>
                  <span className={styles.timeCell}>{toKstTime(it.charged_at)}</span>
                  <span className={styles.labelCell}>{meta.label}</span>
                  <span className={styles.amountCell}>{formatKrw(it.amount_krw)}</span>
                  <span className={styles.emailCell}>{it.user_email_masked}</span>
                  <span className={styles.cardCell}>
                    {it.card_company || ""}
                    {it.card_last4 ? ` ****${it.card_last4}` : ""}
                  </span>
                  <span className={styles.errorCell}>
                    {it.provider_error_code ? (
                      <code className={styles.errorCode}>
                        {it.provider_error_code}
                      </code>
                    ) : (
                      ""
                    )}
                  </span>
                </li>
              );
            })}
          </ul>
        </li>
      ))}
    </ol>
  );
}
