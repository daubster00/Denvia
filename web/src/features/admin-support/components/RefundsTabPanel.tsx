"use client";

import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import type {
  RefundQueueItem,
  RefundQueueStatus,
} from "@/features/admin-support/api/refunds";
import { REFUND_QUEUE_STATUS_LABELS } from "@/features/admin-support/labels";
import { useRefundQueue } from "@/features/admin-support/hooks/useRefundQueue";
import { RefundQueueTable } from "./RefundQueueTable";
import { RefundReviewDrawer } from "./RefundReviewDrawer";
import styles from "./RefundsTabPanel.module.css";

const PER_PAGE = 50;
const STATUS_OPTIONS: RefundQueueStatus[] = ["pending", "approved", "denied"];

function parseStatus(raw: string | null): RefundQueueStatus {
  if (raw === "approved" || raw === "denied" || raw === "pending") {
    return raw;
  }
  return "pending";
}

export function RefundsTabPanel() {
  const searchParams = useSearchParams();
  const initialStatus = parseStatus(searchParams.get("status"));
  const initialQueueIdRaw = searchParams.get("queue_id");
  const initialQueueId =
    initialQueueIdRaw && /^\d+$/.test(initialQueueIdRaw)
      ? Number(initialQueueIdRaw)
      : null;

  const [status, setStatus] = useState<RefundQueueStatus>(initialStatus);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<RefundQueueItem | null>(null);
  const pendingQueueIdRef = useRef<number | null>(initialQueueId);

  const list = useRefundQueue({
    status,
    from: from || undefined,
    to: to || undefined,
    page,
    per_page: PER_PAGE,
  });

  useEffect(() => {
    const target = pendingQueueIdRef.current;
    if (target === null || !list.data) return;
    const hit = list.data.items.find((it) => it.queue_id === target);
    if (hit) {
      setSelected(hit);
      pendingQueueIdRef.current = null;
    } else if (!list.isFetching) {
      pendingQueueIdRef.current = null;
    }
  }, [list.data, list.isFetching]);

  function resetFilters() {
    setStatus("pending");
    setFrom("");
    setTo("");
    setPage(1);
  }

  return (
    <>
      <div className={styles.bar} role="toolbar" aria-label="환불 검토 필터">
        <div className={styles.statusGroup} role="group">
          {STATUS_OPTIONS.map((s) => {
            const active = s === status;
            return (
              <button
                key={s}
                type="button"
                className={
                  active
                    ? `${styles.statusChip} ${styles.statusChipActive}`
                    : styles.statusChip
                }
                aria-pressed={active}
                onClick={() => {
                  setStatus(s);
                  setPage(1);
                }}
              >
                {REFUND_QUEUE_STATUS_LABELS[s]}
              </button>
            );
          })}
        </div>

        <div className={styles.dateGroup}>
          <label className={styles.dateField}>
            <span className={styles.dateLabel}>기간</span>
            <input
              type="date"
              className={styles.dateInput}
              value={from}
              max={to || undefined}
              onChange={(e) => {
                setFrom(e.target.value);
                setPage(1);
              }}
              aria-label="시작일"
            />
          </label>
          <span aria-hidden="true" className={styles.dateSeparator}>
            ~
          </span>
          <label className={styles.dateField}>
            <input
              type="date"
              className={styles.dateInput}
              value={to}
              min={from || undefined}
              onChange={(e) => {
                setTo(e.target.value);
                setPage(1);
              }}
              aria-label="종료일"
            />
          </label>
        </div>

        <button
          type="button"
          className={styles.refreshButton}
          onClick={() => list.refetch()}
          disabled={list.isFetching}
        >
          {list.isFetching ? "..." : "새로고침"}
        </button>
      </div>

      <RefundQueueTable
        data={list.data}
        isLoading={list.isLoading}
        isError={list.isError}
        page={page}
        perPage={PER_PAGE}
        onPageChange={setPage}
        onSelect={(item) => setSelected(item)}
        onResetFilters={resetFilters}
        onRetry={() => list.refetch()}
      />

      <RefundReviewDrawer
        open={selected !== null}
        item={selected}
        onClose={() => setSelected(null)}
      />
    </>
  );
}
