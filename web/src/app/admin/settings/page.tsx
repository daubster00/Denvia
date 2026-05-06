"use client";

import styles from "./page.module.css";

export default function SettingsPage() {
  return (
    <section className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>설정</h1>
        <p className={styles.caption}>서비스 운영 설정을 관리합니다.</p>
      </header>
      <div className={styles.placeholder}>
        <p className={styles.placeholderText}>준비 중입니다.</p>
        <p className={styles.placeholderSub}>설정 관리 기능이 곧 제공됩니다.</p>
      </div>
    </section>
  );
}
