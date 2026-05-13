"use client";

// Story 9.2 — 자동 무료 차단 모드 카드 (읽기 전용).

import Link from "next/link";
import type { AutoFreeOnlyStatus } from "../api/killswitch";
import styles from "./AutoModeCard.module.css";

interface AutoModeCardProps {
  status: AutoFreeOnlyStatus;
}

function formatKstDateTime(iso: string | null): string {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "-";
  // KST = UTC+9
  const kst = new Date(d.getTime() + 9 * 60 * 60 * 1000);
  const yyyy = kst.getUTCFullYear();
  const mm = String(kst.getUTCMonth() + 1).padStart(2, "0");
  const dd = String(kst.getUTCDate()).padStart(2, "0");
  const hh = String(kst.getUTCHours()).padStart(2, "0");
  const mi = String(kst.getUTCMinutes()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd} ${hh}:${mi} (KST)`;
}

export function AutoModeCard({ status }: AutoModeCardProps) {
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
    <section className={cardClass} aria-labelledby="auto-mode-card-title">
      <div className={styles.headerRow}>
        <h3 id="auto-mode-card-title" className={styles.title}>
          자동 무료 차단
        </h3>
        <span className={chipClass}>자동 모드</span>
      </div>

      <p className={styles.cardCode}>auto_free_only</p>

      <div className={styles.statusRow}>
        <span className={dotClass} aria-hidden="true" />
        <span>상태: {status.active ? "ON (활성)" : "OFF"}</span>
      </div>

      <p className={styles.body}>
        {status.active
          ? "예산 사용량이 100%에 도달해 자동 활성화되었습니다. 사용량이 100% 미만으로 내려가면 매시 정각 검사에서 자동 해제됩니다."
          : "현재 예산 사용량은 정상 범위입니다. 100% 도달 시 자동으로 무료 질의가 차단됩니다."}
      </p>

      <ul className={styles.metaList}>
        <li className={styles.metaRow}>
          <span className={styles.metaLabel}>기준월</span>
          <span className={styles.metaValue}>{status.year_month ?? "-"}</span>
        </li>
        <li className={styles.metaRow}>
          <span className={styles.metaLabel}>사용량</span>
          <span className={styles.metaValue}>
            {status.current_percent.toFixed(2)}%
          </span>
        </li>
        <li className={styles.metaRow}>
          <span className={styles.metaLabel}>한도 (USD)</span>
          <span className={styles.metaValue}>${status.monthly_limit_usd}</span>
        </li>
        <li className={styles.metaRow}>
          <span className={styles.metaLabel}>지출 (USD)</span>
          <span className={styles.metaValue}>${status.spent_usd}</span>
        </li>
        {status.active && status.activated_at && (
          <li className={styles.metaRow}>
            <span className={styles.metaLabel}>발동 시각</span>
            <span className={styles.metaValue}>
              {formatKstDateTime(status.activated_at)}
            </span>
          </li>
        )}
      </ul>

      <Link href="/admin/settings#monthly-budget" className={styles.budgetLink}>
        예산 한도 상향 →
      </Link>
    </section>
  );
}
