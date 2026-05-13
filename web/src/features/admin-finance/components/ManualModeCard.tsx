"use client";

// Story 9.2 — 수동 전체 정지 모드 카드 (Danger 영역, 발동/해제 toggle).

import Link from "next/link";
import { useState } from "react";
import type { ManualTotalStatus } from "../api/killswitch";
import { ManualKillSwitchActivateDialog } from "./ManualKillSwitchActivateDialog";
import { ManualKillSwitchDeactivateDialog } from "./ManualKillSwitchDeactivateDialog";
import styles from "./ManualModeCard.module.css";

interface ManualModeCardProps {
  status: ManualTotalStatus;
}

function formatKstDateTime(iso: string | null): string {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "-";
  const kst = new Date(d.getTime() + 9 * 60 * 60 * 1000);
  const yyyy = kst.getUTCFullYear();
  const mm = String(kst.getUTCMonth() + 1).padStart(2, "0");
  const dd = String(kst.getUTCDate()).padStart(2, "0");
  const hh = String(kst.getUTCHours()).padStart(2, "0");
  const mi = String(kst.getUTCMinutes()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd} ${hh}:${mi} (KST)`;
}

export function ManualModeCard({ status }: ManualModeCardProps) {
  const [activateOpen, setActivateOpen] = useState(false);
  const [deactivateOpen, setDeactivateOpen] = useState(false);

  const cardClass = status.active
    ? `${styles.card} ${styles.cardActive}`
    : styles.card;
  const dotClass = status.active
    ? `${styles.statusDot} ${styles.statusDotActive}`
    : styles.statusDot;
  const chipClass = status.active
    ? `${styles.modeChip} ${styles.modeChipActive}`
    : styles.modeChip;

  return (
    <section className={cardClass} aria-labelledby="manual-mode-card-title">
      <div className={styles.headerRow}>
        <div className={styles.titleGroup}>
          <h3 id="manual-mode-card-title" className={styles.title}>
            수동 전체 정지
          </h3>
          <span className={styles.dangerChip}>위험</span>
        </div>
        <span className={chipClass}>수동 모드</span>
      </div>

      <p className={styles.cardCode}>manual_total</p>

      <div className={styles.statusRow}>
        <span className={dotClass} aria-hidden="true" />
        <span>상태: {status.active ? "ON (활성)" : "OFF"}</span>
      </div>

      {status.active ? (
        <>
          <ul className={styles.metaList}>
            <li className={styles.metaRow}>
              <span className={styles.metaLabel}>발동 시각</span>
              <span className={styles.metaValue}>
                {formatKstDateTime(status.activated_at)}
              </span>
            </li>
            <li className={styles.metaRow}>
              <span className={styles.metaLabel}>발동자</span>
              <span className={styles.metaValue}>
                {status.activated_by_admin_email ?? "-"}
              </span>
            </li>
          </ul>
          {status.reason && (
            <div className={styles.reasonBlock}>{status.reason}</div>
          )}
        </>
      ) : (
        <p className={styles.body}>
          비상시 모든 사용자(무료·유료 모두)의 신규 질의를 즉시 차단합니다. 발동 시점부터
          해제 시점까지의 기간만큼 활성 유료 구독자의 만료일이 자동으로 연장됩니다.
        </p>
      )}

      <div className={styles.actionRow}>
        {status.active ? (
          <button
            type="button"
            className={styles.primaryBtn}
            onClick={() => setDeactivateOpen(true)}
          >
            ↻ 전체 정지 해제
          </button>
        ) : (
          <button
            type="button"
            className={styles.dangerBtn}
            onClick={() => setActivateOpen(true)}
          >
            ⚠ 전체 정지 발동
          </button>
        )}
      </div>

      <Link
        href="/legal/terms#killswitch-extension"
        className={styles.termsLink}
      >
        이용약관 §N(자동 연장 조항) →
      </Link>

      <ManualKillSwitchActivateDialog
        open={activateOpen}
        onClose={() => setActivateOpen(false)}
      />
      <ManualKillSwitchDeactivateDialog
        open={deactivateOpen}
        onClose={() => setDeactivateOpen(false)}
        durationActivatedAt={status.activated_at}
      />
    </section>
  );
}
