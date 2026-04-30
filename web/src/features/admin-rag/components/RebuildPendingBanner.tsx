"use client";

import { IconCircleExclamationFill } from "@wanteddev/wds-icon";
import styles from "./RebuildPendingBanner.module.css";

interface Props {
  pendingCount: number;
  onRebuild?: () => void;
  isRebuilding?: boolean;
}

export function RebuildPendingBanner({ pendingCount, onRebuild, isRebuilding }: Props) {
  if (pendingCount === 0) return null;
  return (
    <div role="alert" className={styles.banner}>
      <span className={styles.icon} aria-hidden="true">
        <IconCircleExclamationFill />
      </span>
      <span className={styles.message}>
        변경사항이 <strong>{pendingCount}건</strong> 있습니다. 재빌드를 실행해 검색에 반영하세요.
      </span>
      <button
        type="button"
        onClick={onRebuild}
        disabled={isRebuilding}
        title={isRebuilding ? "재빌드가 이미 진행 중입니다" : undefined}
        className={styles.rebuildBtn}
      >
        {isRebuilding ? "재빌드 진행 중" : "재빌드 실행"}
      </button>
    </div>
  );
}
