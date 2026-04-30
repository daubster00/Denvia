"use client";

import { useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchRagStatus, type RagStatusResponse } from "@/features/admin-rag/api/knowledge";
import { useAdminEventsStore } from "@/stores/admin-events-store";
import {
  DashboardWidget,
  WidgetErrorState,
  WidgetLoadingState,
} from "./DashboardWidget";
import styles from "./RagStatusWidget.module.css";

const QUERY_KEY = ["admin", "dashboard", "rag-status"] as const;

export function RagStatusWidget() {
  const qc = useQueryClient();
  const rebuildProgress = useAdminEventsStore((s) => s.rebuildProgress);

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: QUERY_KEY,
    queryFn: fetchRagStatus,
    refetchInterval: (query) =>
      query.state.data?.active_rebuild ? 5_000 : 60_000,
  });

  useEffect(() => {
    if (rebuildProgress) qc.invalidateQueries({ queryKey: QUERY_KEY });
  }, [rebuildProgress, qc]);

  return (
    <DashboardWidget
      title="RAG 인덱스 상태"
      caption="치과 지식 인덱스 변경/재빌드 현황을 확인합니다."
      detailHref="/admin/rag/data"
      detailLabel="RAG 데이터로 이동"
    >
      {isLoading && <WidgetLoadingState />}
      {!isLoading && (error || !data) && (
        <WidgetErrorState onRetry={() => refetch()} />
      )}
      {data && <RagStatusBody data={data} />}
    </DashboardWidget>
  );
}

function RagStatusBody({ data }: { data: RagStatusResponse }) {
  const formattedAt = data.last_rebuild_at
    ? new Date(data.last_rebuild_at).toLocaleString("ko-KR", {
        timeZone: "Asia/Seoul",
      })
    : "—";

  const hasPending = data.pending_changes_count > 0;
  const active = data.active_rebuild;
  const progress = active ? Math.max(0, Math.min(100, active.progress_percent)) : 0;

  return (
    <div className={styles.body}>
      <div className={styles.row}>
        <span className={styles.label}>대기 중 변경</span>
        {hasPending ? (
          <span className={`${styles.badge} ${styles.badgePending}`}>
            재빌드 대기 {data.pending_changes_count}건
          </span>
        ) : (
          <span className={`${styles.badge} ${styles.badgeFresh}`}>최신</span>
        )}
      </div>
      <div className={styles.row}>
        <span className={styles.label}>마지막 재빌드</span>
        <span className={styles.value}>{formattedAt}</span>
      </div>
      <div className={styles.row}>
        <span className={styles.label}>마지막 결과</span>
        <RebuildStatusBadge status={data.last_rebuild_status} />
      </div>
      {active && (
        <div className={styles.progressWrap}>
          <div className={styles.progressTop}>
            <span>{active.stage ?? "진행 중"}</span>
            <span>{progress}%</span>
          </div>
          <div
            className={styles.progressTrack}
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={progress}
            aria-label="재빌드 진행률"
          >
            <div className={styles.progressFill} style={{ width: `${progress}%` }} />
          </div>
        </div>
      )}
    </div>
  );
}

function RebuildStatusBadge({ status }: { status: string | null }) {
  if (!status) return <span className={styles.value}>—</span>;
  if (status === "success")
    return <span className={`${styles.badge} ${styles.badgeSuccess}`}>성공</span>;
  if (status === "failed")
    return <span className={`${styles.badge} ${styles.badgeFailed}`}>실패</span>;
  if (status === "canceled")
    return <span className={`${styles.badge} ${styles.badgeCanceled}`}>취소됨</span>;
  return <span className={styles.value}>{status}</span>;
}
