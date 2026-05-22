"use client";

import { useState } from "react";
import { useSearchParams } from "next/navigation";
import { AnomalyTabs } from "@/features/admin-anomaly/components/AnomalyTabs";
import { AnomalyTable } from "@/features/admin-anomaly/components/AnomalyTable";
import { AnomalyDetailDrawer } from "@/features/admin-anomaly/components/AnomalyDetailDrawer";
import { useAnomalyList } from "@/features/admin-anomaly/hooks/useAnomalyList";
import type {
  AnomalyEventItem,
  AnomalyStatus,
  AnomalyType,
} from "@/features/admin-anomaly/api/anomaly";
import styles from "./page.module.css";

const PER_PAGE = 20;

const STATUS_OPTIONS: { label: string; value: AnomalyStatus[] }[] = [
  { label: "미검토", value: ["new"] },
  { label: "검토완료", value: ["reviewed"] },
  { label: "처리됨", value: ["actioned"] },
  { label: "전체", value: ["new", "reviewed", "actioned"] },
];

const VALID_TYPES: AnomalyType[] = [
  "login_brute_force",
  "concurrent_ip_login",
  "repeated_question",
  "recovery_abuse",
  "rapid_followup_questions",
];

const VALID_STATUSES: AnomalyStatus[] = ["new", "reviewed", "actioned"];

export default function AnomalyPage() {
  const searchParams = useSearchParams();
  const initialType = (() => {
    const raw = searchParams.get("type");
    return raw && (VALID_TYPES as string[]).includes(raw)
      ? (raw as AnomalyType)
      : null;
  })();
  const initialStatus = (() => {
    const raw = searchParams.get("status");
    if (raw && (VALID_STATUSES as string[]).includes(raw)) {
      return [raw as AnomalyStatus];
    }
    return ["new"] as AnomalyStatus[];
  })();

  const [activeType, setActiveType] = useState<AnomalyType | null>(initialType);
  const [statusIn, setStatusIn] = useState<AnomalyStatus[]>(initialStatus);
  const [page, setPage] = useState(1);
  const [openedAnomalyId, setOpenedAnomalyId] = useState<number | null>(null);

  const { data, isLoading, isError, refetch } = useAnomalyList({
    type_in: activeType ? [activeType] : undefined,
    status_in: statusIn,
    page,
    per_page: PER_PAGE,
  });

  function handleTypeChange(next: AnomalyType | null) {
    setActiveType(next);
    setPage(1);
  }

  function handleStatusChange(next: AnomalyStatus[]) {
    setStatusIn(next);
    setPage(1);
  }

  function handleShowDetail(anomaly: AnomalyEventItem) {
    setOpenedAnomalyId(anomaly.id);
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
        onShowDetail={handleShowDetail}
        onRetry={() => refetch()}
      />

      {openedAnomalyId !== null ? (
        <AnomalyDetailDrawer
          anomalyId={openedAnomalyId}
          onClose={() => setOpenedAnomalyId(null)}
        />
      ) : null}
    </section>
  );
}
