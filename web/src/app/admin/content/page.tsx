"use client";

import { AnomalyThrottleForm } from "@/features/admin-content/components/AnomalyThrottleForm";
import { ServiceTogglesForm } from "@/features/admin-content/components/ServiceTogglesForm";
import styles from "./page.module.css";

export default function AdminContentHubPage() {
  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.heading}>컨텐츠 관리</h1>
        <p className={styles.subheading}>
          서비스 전체에 적용되는 토글을 관리합니다. 팝업·공지 관리는 좌측 사이드바의 하위 메뉴에서 이동합니다.
        </p>
      </header>

      <ServiceTogglesForm />
      <AnomalyThrottleForm />
    </main>
  );
}
