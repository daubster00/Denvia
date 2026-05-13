"use client";

import { use } from "react";
import Link from "next/link";
import { UserDetailView } from "@/features/admin-users/components/UserDetailView";
import { useUserDetail } from "@/features/admin-users/hooks/useUserDetail";
import styles from "./page.module.css";

interface PageProps {
  params: Promise<{ userId: string }>;
}

function parseUserId(raw: string): number | null {
  if (!/^\d+$/.test(raw)) return null;
  const n = Number(raw);
  return Number.isInteger(n) && n >= 1 ? n : null;
}

export default function AdminUserDetailPage({ params }: PageProps) {
  const { userId: userIdRaw } = use(params);
  const userId = parseUserId(userIdRaw);

  const detail = useUserDetail(userId);

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
    <section className={styles.page} aria-labelledby="admin-user-detail-title">
      <div className={styles.breadcrumb}>
        <Link href="/admin/users" className={styles.backLink}>
          ← 고객 관리
        </Link>
      </div>

      <header className={styles.header}>
        <div className={styles.titleGroup}>
          <h1 id="admin-user-detail-title" className={styles.title}>
            사용자 상세
          </h1>
          <p className={styles.caption}>
            기본 정보 · 결제 정보 · 이상 이벤트 · 최근 질의를 한 화면에서 확인합니다.
          </p>
        </div>
      </header>

      <UserDetailView
        detail={detail.data}
        isLoading={detail.isLoading}
        isError={detail.isError}
        onRetry={() => detail.refetch()}
        onPermissionUpdated={() => detail.refetch()}
      />
    </section>
  );
}
