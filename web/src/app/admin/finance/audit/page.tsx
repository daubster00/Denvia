"use client";

import { useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import type { AuditLogItem } from "@/features/admin-users/api/audit";
import { useAuditLogs } from "@/features/admin-users/hooks/useAuditLogs";
import { FinanceAuditTable } from "@/features/admin-finance/components/FinanceAuditTable";
import { FinanceAuditDetailModal } from "@/features/admin-finance/components/FinanceAuditDetailModal";
import { FINANCE_AUDIT_ACTIONS } from "@/features/admin-finance/labels";
import styles from "./page.module.css";

const PER_PAGE = 20;
const ALL_ACTION_VALUES = FINANCE_AUDIT_ACTIONS.map((a) => a.value);

function parseActionInParam(raw: string | null): string[] {
  if (!raw) return ALL_ACTION_VALUES;
  const tokens = raw
    .split(",")
    .map((t) => t.trim())
    .filter((t) => ALL_ACTION_VALUES.includes(t));
  return tokens.length > 0 ? tokens : ALL_ACTION_VALUES;
}

export default function AdminFinanceAuditPage() {
  const router = useRouter();
  const params = useSearchParams();

  const targetIdRaw = params.get("target_id");
  const targetId =
    targetIdRaw && /^\d+$/.test(targetIdRaw) ? Number(targetIdRaw) : undefined;

  const [selectedActions, setSelectedActions] = useState<string[]>(() =>
    parseActionInParam(params.get("action_in")),
  );
  const [page, setPage] = useState(1);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [activeLog, setActiveLog] = useState<AuditLogItem | undefined>();

  const { data, isLoading, isError } = useAuditLogs({
    action_in: selectedActions.length > 0 ? selectedActions : undefined,
    target_id: targetId,
    page,
    per_page: PER_PAGE,
  });

  const items = useMemo(() => data?.items ?? [], [data]);

  function toggleAction(value: string) {
    setSelectedActions((prev) =>
      prev.includes(value) ? prev.filter((v) => v !== value) : [...prev, value],
    );
    setPage(1);
  }

  function resetFilters() {
    setSelectedActions(ALL_ACTION_VALUES);
    setPage(1);
  }

  function clearTargetId() {
    const next = new URLSearchParams(params.toString());
    next.delete("target_id");
    router.replace(`/admin/finance/audit?${next.toString()}`);
    setPage(1);
  }

  function handleSelect(log: AuditLogItem) {
    setActiveLog(log);
    setDrawerOpen(true);
  }

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>결제 감사 로그</h1>
        <p className={styles.subtitle}>
          관리자가 처리한 환불 승인·거부 + 비상정지로 인한 자동 구독 연장 기록
        </p>
      </header>

      <section className={styles.filters}>
        <div className={styles.filterGroup}>
          <span className={styles.filterLabel}>액션</span>
          <div className={styles.checkboxRow}>
            {FINANCE_AUDIT_ACTIONS.map((action) => (
              <label key={action.value} className={styles.checkboxLabel}>
                <input
                  type="checkbox"
                  checked={selectedActions.includes(action.value)}
                  onChange={() => toggleAction(action.value)}
                  data-testid={`finance-audit-filter-${action.value}`}
                />
                <span>{action.label}</span>
              </label>
            ))}
          </div>
        </div>

        {targetId !== undefined ? (
          <div className={styles.filterGroup}>
            <span className={styles.filterLabel}>대상 ID 필터</span>
            <span
              className={styles.contextChip}
              data-testid="finance-audit-target-chip"
            >
              <span>#{targetId}</span>
              <button
                type="button"
                className={styles.clearLink}
                onClick={clearTargetId}
              >
                해제
              </button>
            </span>
          </div>
        ) : null}
      </section>

      <p className={styles.totalCount}>
        전체 {(data?.total ?? 0).toLocaleString("ko-KR")}건
      </p>

      <FinanceAuditTable
        items={items}
        page={page}
        perPage={PER_PAGE}
        total={data?.total ?? 0}
        isLoading={isLoading}
        isError={isError}
        onPageChange={setPage}
        onSelect={handleSelect}
        onResetFilters={resetFilters}
      />

      <FinanceAuditDetailModal
        open={drawerOpen}
        log={activeLog}
        onClose={() => setDrawerOpen(false)}
      />
    </main>
  );
}
