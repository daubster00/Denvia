"use client";

import { KillSwitchPanel } from "@/features/admin-finance/components/KillSwitchPanel";
import styles from "./page.module.css";

export default function FinanceKillswitchPage() {
  return (
    <section className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>비상 정지(킬스위치)</h1>
        <p className={styles.caption}>
          자동 무료 차단(예산 100% 도달)과 수동 전체 정지(비상시)를 한 화면에서
          통합 운영합니다. 수동 정지 기간만큼 활성 유료 구독자의 만료일이 자동으로
          연장됩니다.
        </p>
      </header>

      <KillSwitchPanel />
    </section>
  );
}
