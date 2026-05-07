"use client";

import styles from "./page.module.css";

export default function FinancePage() {
  return (
    <section className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>재무</h1>
        <p className={styles.caption}>예산 및 토큰 비용 현황을 관리합니다.</p>
      </header>

      <div className={styles.placeholder} role="status">
        <span className={styles.badge}>준비 중</span>
        <p className={styles.placeholderTitle}>재무 화면을 준비 중입니다</p>
        <p className={styles.placeholderDesc}>
          매출 대시보드, 예산 경고, 킬스위치 패널 등 재무 관련 기능은 후속
          스토리에서 순차적으로 공개됩니다.
        </p>
      </div>
    </section>
  );
}
