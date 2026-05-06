"use client";

import { useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { AuditDiffDrawer } from "@/features/admin-users/components/AuditDiffDrawer";
import { UserEditHistoryTable } from "@/features/admin-users/components/UserEditHistoryTable";
import type { AuditLogItem } from "@/features/admin-users/api/audit";
import { useAuditLogs } from "@/features/admin-users/hooks/useAuditLogs";
import styles from "./page.module.css";

const ALL_ACTIONS = [
  { value: "user.permission_edit", label: "권한 수정" },
  { value: "user.speed_override", label: "속도 변경" },
  { value: "user.block_auto_expired", label: "자동 차단 만료" },
];

const PER_PAGE = 20;

export default function AdminUsersEditsPage() {
  const params = useSearchParams();
  const userIdRaw = params.get("user_id");
  const targetIdInitial = userIdRaw && /^\d+$/.test(userIdRaw)
    ? Number(userIdRaw)
    : undefined;

  const [selectedActions, setSelectedActions] = useState<string[]>(
    ALL_ACTIONS.map((a) => a.value),
  );
  const [targetId, setTargetId] = useState<number | undefined>(targetIdInitial);
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
    setSelectedActions(ALL_ACTIONS.map((a) => a.value));
    setTargetId(undefined);
    setPage(1);
  }

  function handleSelect(log: AuditLogItem) {
    setActiveLog(log);
    setDrawerOpen(true);
  }

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>사용자 수정 이력</h1>
        <p className={styles.subtitle}>
          관리자가 수행한 권한·차단·한도 변경 이력 + 자동 차단 만료 기록
        </p>
      </header>

      <section className={styles.filters}>
        <div className={styles.filterGroup}>
          <span className={styles.filterLabel}>액션</span>
          <div className={styles.checkboxRow}>
            {ALL_ACTIONS.map((action) => (
              <label key={action.value} className={styles.checkboxLabel}>
                <input
                  type="checkbox"
                  checked={selectedActions.includes(action.value)}
                  onChange={() => toggleAction(action.value)}
                  data-testid={`action-filter-${action.value}`}
                />
                <span>{action.label}</span>
              </label>
            ))}
          </div>
        </div>

        <div className={styles.filterGroup}>
          <label htmlFor="target-id-input" className={styles.filterLabel}>
            대상 사용자 ID
          </label>
          <div className={styles.idRow}>
            <input
              id="target-id-input"
              type="number"
              min={1}
              value={targetId ?? ""}
              onChange={(e) => {
                const v = e.target.value;
                if (!v) {
                  setTargetId(undefined);
                  setPage(1);
                  return;
                }
                const parsed = Number(v);
                if (Number.isInteger(parsed) && parsed >= 1) {
                  setTargetId(parsed);
                  setPage(1);
                }
              }}
              className={styles.idInput}
              placeholder="예: 12"
              data-testid="target-id-input"
            />
            {targetId !== undefined ? (
              <button
                type="button"
                onClick={() => {
                  setTargetId(undefined);
                  setPage(1);
                }}
                className={styles.clearButton}
                data-testid="clear-target-id"
              >
                초기화
              </button>
            ) : null}
          </div>
        </div>
      </section>

      <UserEditHistoryTable
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

      <AuditDiffDrawer
        open={drawerOpen}
        log={activeLog}
        onClose={() => setDrawerOpen(false)}
      />
    </main>
  );
}
