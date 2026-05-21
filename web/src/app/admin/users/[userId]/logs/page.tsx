"use client";

import { use } from "react";
import Link from "next/link";
import { UserActivityLogs } from "@/features/admin-users/components/UserActivityLogs";
import styles from "./page.module.css";

interface PageProps {
  params: Promise<{ userId: string }>;
}

function parseUserId(raw: string): number | null {
  if (!/^\d+$/.test(raw)) return null;
  const n = Number(raw);
  return Number.isInteger(n) && n >= 1 ? n : null;
}

export default function AdminUserLogsPage({ params }: PageProps) {
  const { userId: userIdRaw } = use(params);
  const userId = parseUserId(userIdRaw);

  if (userId === null) {
    return (
      <section className={styles.page}>
        <div className={styles.breadcrumb}>
          <Link href="/admin/users" className={styles.backLink}>
            ← 고객 관리
          </Link>
        </div>
        <div className={styles.invalidBox} role="alert">
          잘못된 사용자 ID입니다.
        </div>
      </section>
    );
  }

  return (
    <section className={styles.page} aria-labelledby="admin-user-logs-title">
      <div className={styles.breadcrumb}>
        <Link href={`/admin/users/${userId}`} className={styles.backLink}>
          ← 사용자 상세
        </Link>
      </div>

      <header className={styles.header}>
        <h1 id="admin-user-logs-title" className={styles.title}>
          사용자 로그 기록
        </h1>
        <p className={styles.caption}>
          이 사용자가 활동한 질의·문의·결제·이상 이벤트·권한 변경 기록을 한
          화면에서 확인합니다.
        </p>
      </header>

      <UserActivityLogs userId={userId} />
    </section>
  );
}
