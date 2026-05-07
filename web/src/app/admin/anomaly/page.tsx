"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { AnomalyTabs } from "@/features/admin-anomaly/components/AnomalyTabs";
import { AnomalyTable } from "@/features/admin-anomaly/components/AnomalyTable";
import { useAnomalyList } from "@/features/admin-anomaly/hooks/useAnomalyList";
import { useMarkReviewed } from "@/features/admin-anomaly/hooks/useMarkReviewed";
import type {
  AnomalyEventItem,
  AnomalyStatus,
  AnomalyType,
} from "@/features/admin-anomaly/api/anomaly";
import { useUpdatePermission } from "@/features/admin-users/hooks/useUpdatePermission";
import { useToastStore } from "@/stores/toast-store";
import styles from "./page.module.css";

const PER_PAGE = 20;

const STATUS_OPTIONS: { label: string; value: AnomalyStatus[] }[] = [
  { label: "미검토", value: ["new"] },
  { label: "검토완료", value: ["reviewed"] },
  { label: "처리됨", value: ["actioned"] },
  { label: "전체", value: ["new", "reviewed", "actioned"] },
];

export default function AnomalyPage() {
  const [activeType, setActiveType] = useState<AnomalyType | null>(null);
  const [statusIn, setStatusIn] = useState<AnomalyStatus[]>(["new"]);
  const [page, setPage] = useState(1);

  const qc = useQueryClient();
  const showToast = useToastStore((s) => s.show);

  const { data, isLoading, isError, refetch } = useAnomalyList({
    type_in: activeType ? [activeType] : undefined,
    status_in: statusIn,
    page,
    per_page: PER_PAGE,
  });

  const markReviewed = useMarkReviewed();
  const updatePermission = useUpdatePermission();

  function handleTypeChange(next: AnomalyType | null) {
    setActiveType(next);
    setPage(1);
  }

  function handleStatusChange(next: AnomalyStatus[]) {
    setStatusIn(next);
    setPage(1);
  }

  async function handleApplyBlock(
    anomaly: AnomalyEventItem,
    durationHours: number | null,
  ) {
    if (!anomaly.target_user_id) {
      showToast("IP 기반 이벤트는 사용자 차단을 적용할 수 없습니다.");
      return;
    }
    const label =
      durationHours === null
        ? "영구 차단"
        : durationHours === 24
          ? "24시간 차단"
          : "7일 차단";
    try {
      await updatePermission.mutateAsync({
        userId: anomaly.target_user_id,
        payload: {
          block_action: {
            duration_hours: durationHours,
            reason: `이상행동 탐지 (${anomaly.type})`,
          },
        },
      });
      await qc.invalidateQueries({ queryKey: ["admin", "anomaly"] });
      showToast(`${label} 처리되었습니다.`);
    } catch {
      showToast("차단 처리에 실패했습니다. 다시 시도해주세요.");
    }
  }

  function handleMarkReviewed(anomaly: AnomalyEventItem) {
    markReviewed.mutate(anomaly.id, {
      onSuccess: () => showToast("검토 완료 처리되었습니다."),
      onError: () => showToast("검토 처리에 실패했습니다."),
    });
  }

  const isStatusActive = (opt: AnomalyStatus[]) =>
    opt.length === statusIn.length && opt.every((s) => statusIn.includes(s));

  return (
    <section className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>이상탐지</h1>
        <p className={styles.caption}>
          비정상적인 사용 패턴과 보안 이벤트를 모니터링합니다.
        </p>
      </header>

      <AnomalyTabs activeType={activeType} onChange={handleTypeChange} />

      <div className={styles.controls}>
        <div
          className={styles.statusFilter}
          role="group"
          aria-label="상태 필터"
        >
          {STATUS_OPTIONS.map((opt) => (
            <button
              key={opt.value.join(",")}
              type="button"
              className={
                isStatusActive(opt.value)
                  ? styles.statusBtnActive
                  : styles.statusBtn
              }
              onClick={() => handleStatusChange(opt.value)}
            >
              {opt.label}
            </button>
          ))}
        </div>
        <button
          type="button"
          className={styles.refreshButton}
          onClick={() => refetch()}
          disabled={isLoading}
        >
          새로고침
        </button>
      </div>

      <AnomalyTable
        data={data}
        isLoading={isLoading}
        isError={isError}
        page={page}
        perPage={PER_PAGE}
        onPageChange={setPage}
        onApplyBlock={handleApplyBlock}
        onMarkReviewed={handleMarkReviewed}
        onRetry={() => refetch()}
      />
    </section>
  );
}
