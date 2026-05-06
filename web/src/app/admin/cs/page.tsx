"use client";

import styles from "./page.module.css";

export default function CsPage() {
  return (
    <section className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>CS</h1>
        <p className={styles.caption}>고객 문의와 처리 현황을 관리합니다.</p>
      </header>
      <div className={styles.placeholder}>
        <p className={styles.placeholderText}>준비 중입니다.</p>
        <p className={styles.placeholderSub}>CS 관리 기능이 곧 제공됩니다.</p>
      </div>
    </section>
  );
}
