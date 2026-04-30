"use client";

import styles from "./IndexStatusCard.module.css";

interface Props {
  pendingChangesCount: number;
  lastRebuildAt?: string | null;
  lastRebuildStatus?: string | null;
  isRebuilding?: boolean;
  rebuildProgress?: number;
  onRebuild?: () => void;
}

function RebuildStatusBadge({ status }: { status: string | null | undefined }) {
  if (!status) return <span className={styles.value}>—</span>;
  if (status === "success") return <span className={`${styles.badge} ${styles.badgeSuccess}`}>성공</span>;
  if (status === "failed") return <span className={`${styles.badge} ${styles.badgeFailed}`}>실패</span>;
  if (status === "canceled") return <span className={`${styles.badge} ${styles.badgeCanceled}`}>취소됨</span>;
  return <span className={styles.value}>{status}</span>;
}

export function IndexStatusCard({
  pendingChangesCount,
  lastRebuildAt,
  lastRebuildStatus,
  isRebuilding = false,
  rebuildProgress = 0,
  onRebuild,
}: Props) {
  const formattedAt = lastRebuildAt
    ? new Date(lastRebuildAt).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" })
    : null;

  const hasPending = pendingChangesCount > 0;
  const buttonActive = hasPending && !isRebuilding;
  const gaugeActive = isRebuilding;
  const gaugePercent = gaugeActive ? Math.max(0, Math.min(100, rebuildProgress)) : 0;

  const guidance = isRebuilding
    ? `재빌드가 진행 중입니다. (${gaugePercent}%) 완료될 때까지 기다려 주세요.`
    : hasPending
      ? `변경사항이 ${pendingChangesCount}건 있습니다. 재빌드를 실행해 검색에 반영하세요.`
      : "변경사항이 없습니다. 새 파일을 업로드하거나 편집하면 재빌드가 필요합니다.";

  return (
    <section className={styles.card}>
      <div className={styles.header}>
        <div className={styles.titleGroup}>
          <h2 className={styles.title}>재빌드 상태</h2>
          <p className={styles.guidance}>{guidance}</p>
        </div>
        <button
          type="button"
          onClick={onRebuild}
          disabled={!buttonActive}
          className={`${styles.rebuildBtn} ${buttonActive ? styles.rebuildBtnActive : styles.rebuildBtnInactive}`}
          title={
            isRebuilding
              ? "재빌드가 이미 진행 중입니다"
              : !hasPending
                ? "재빌드할 변경사항이 없습니다"
                : undefined
          }
        >
          {isRebuilding ? "재빌드 진행 중" : "재빌드 실행"}
        </button>
      </div>

      <div className={styles.box}>
        <div className={styles.body}>
          <div className={styles.stats}>
            <div className={styles.item}>
              <span className={styles.label}>마지막 재빌드</span>
              <span className={styles.value}>{formattedAt ?? "—"}</span>
            </div>
            <div className={styles.item}>
              <span className={styles.label}>재빌드 상태</span>
              <RebuildStatusBadge status={lastRebuildStatus} />
            </div>
            <div className={styles.item}>
              <span className={styles.label}>상태</span>
              {hasPending ? (
                <span className={styles.badge}>재빌드 대기 {pendingChangesCount}건</span>
              ) : (
                <span className={styles.value}>최신</span>
              )}
            </div>
          </div>

          <div className={styles.gaugeWrap}>
            <div
              className={`${styles.gauge} ${gaugeActive ? styles.gaugeActive : styles.gaugeInactive}`}
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={gaugePercent}
              aria-label="재빌드 진행률"
            >
              <div
                className={styles.gaugeFill}
                style={{ width: `${gaugePercent}%` }}
              />
            </div>
            <span
              className={`${styles.gaugePercent} ${gaugeActive ? styles.gaugePercentActive : ""}`}
              aria-hidden="true"
            >
              {gaugePercent}%
            </span>
          </div>
        </div>
      </div>
    </section>
  );
}
