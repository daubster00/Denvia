"use client";

import styles from "./page.module.css";

export default function AnomalyPage() {
  return (
    <section className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>이상탐지</h1>
        <p className={styles.caption}>비정상적인 사용 패턴과 보안 이벤트를 모니터링합니다.</p>
      </header>
      <div className={styles.placeholder}>
        <p className={styles.placeholderText}>준비 중입니다.</p>
        <p className={styles.placeholderSub}>이상탐지 대시보드가 곧 제공됩니다.</p>
      </div>
    </section>
  );
}
