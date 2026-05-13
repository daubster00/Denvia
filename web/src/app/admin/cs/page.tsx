"use client";

import { InquiriesTabPanel } from "@/features/admin-support/components/InquiriesTabPanel";
import styles from "./page.module.css";

export default function CsPage() {
  return (
    <section className={styles.page} aria-labelledby="admin-cs-title">
      <header className={styles.header}>
        <div className={styles.titleGroup}>
          <h1 id="admin-cs-title" className={styles.title}>
            CS
          </h1>
          <p className={styles.caption}>
            고객 문의를 검토·응답합니다. 답변은 사용자에게 알림톡과 쪽지함으로
            즉시 발송됩니다.
          </p>
        </div>
      </header>

      <InquiriesTabPanel />
    </section>
  );
}
