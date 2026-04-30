"use client";

import styles from "./BudgetGauge.module.css";

interface Props {
  current: number;
  max: number;
  warningThreshold?: number;
  dangerThreshold?: number;
  killswitchActive?: boolean;
  killswitchMode?: "auto_free_only" | "manual_total" | null;
}

export function BudgetGauge({
  current,
  max,
  warningThreshold = 80,
  dangerThreshold = 95,
  killswitchActive = false,
  killswitchMode = null,
}: Props) {
  const percent = max > 0 ? Math.min((current / max) * 100, 100) : 0;
  const state =
    percent >= dangerThreshold
      ? "danger"
      : percent >= warningThreshold
        ? "warning"
        : "normal";
  const label =
    state === "danger" ? "위험" : state === "warning" ? "주의" : "정상";

  return (
    <div className={styles.container}>
      {killswitchActive && (
        <p className={styles.killswitchNote}>
          {killswitchMode === "manual_total"
            ? "수동 비상 정지 활성 — 전체 질의 차단"
            : "예산 한도 도달 — 무료 질의 자동 차단 활성"}
        </p>
      )}
      <div
        className={`${styles.gaugeTrack} ${styles[state]}`}
        role="progressbar"
        aria-valuenow={Math.round(percent)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="월 예산 사용률"
      >
        <div className={styles.fill} style={{ width: `${percent}%` }} />
        {state !== "normal" && (
          <span
            className={styles.marker80}
            style={{ left: `${warningThreshold}%` }}
            aria-hidden="true"
          />
        )}
        {state === "danger" && (
          <span
            className={styles.marker95}
            style={{ left: `${dangerThreshold}%` }}
            aria-hidden="true"
          />
        )}
      </div>
      <p className={styles.statusText}>
        <span className={styles[`statusLabel_${state}`]}>{label}</span>
        {" — "}
        {percent.toFixed(2)}% 사용
      </p>
      {state === "danger" && (
        <p className={styles.caption}>
          예산 소진 시 무료 질의 자동 차단
        </p>
      )}
    </div>
  );
}
