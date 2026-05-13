"use client";

// Story 9.2 — KillSwitchPanel: 자동(읽기 전용) + 수동(Danger toggle) 2-card grid.

import { AutoModeCard } from "./AutoModeCard";
import { ManualModeCard } from "./ManualModeCard";
import { useKillswitchStatus } from "../hooks/useKillswitchStatus";
import styles from "./KillSwitchPanel.module.css";

export function KillSwitchPanel() {
  const { data, isLoading, isError, refetch } = useKillswitchStatus();

  if (isLoading) {
    return (
      <div className={styles.stateBox} role="status" aria-live="polite">
        킬스위치 상태를 불러오는 중…
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className={`${styles.stateBox} ${styles.stateError}`} role="alert">
        킬스위치 상태를 불러오지 못했습니다.{" "}
        <button type="button" onClick={() => refetch()}>
          다시 시도
        </button>
      </div>
    );
  }

  return (
    <div className={styles.panel}>
      <div className={styles.cardGrid}>
        <AutoModeCard status={data.auto_free_only} />
        <ManualModeCard status={data.manual_total} />
      </div>
    </div>
  );
}
