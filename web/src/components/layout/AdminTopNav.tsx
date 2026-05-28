"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { useAdminSessionStore } from "@/stores/admin-session-store";
import { adminLogout } from "@/features/admin-auth/api";
import { LogoLink } from "@/components/brand/LogoLink";
import { AdminWarmupToggle } from "./AdminWarmupToggle";
import styles from "./AdminTopNav.module.css";

export function AdminTopNav() {
  const router = useRouter();
  const admin = useAdminSessionStore((s) => s.admin);
  const clearAdmin = useAdminSessionStore((s) => s.clearAdmin);
  const queryClient = useQueryClient();

  const handleLogout = async () => {
    try {
      await adminLogout();
    } finally {
      clearAdmin();
      queryClient.removeQueries({ queryKey: ["admin-session"] });
      router.replace("/admin/login");
    }
  };

  const gradeLabel = admin?.is_master ? "마스터" : "관리자";

  return (
    <header className={styles.header}>
      <LogoLink href="/admin" ariaLabel="관리자 대시보드" />

      <div className={styles.right}>
        <AdminWarmupToggle isMaster={admin?.is_master ?? false} />
        {admin && (
          <Link
            href="/admin/account"
            className={styles.accountLink}
            aria-label="관리자 계정 정보 수정"
            title="계정 정보 수정"
          >
            <span className={styles.accountInfo}>
              <span className={styles.email}>{admin.email}</span>
              <span
                className={
                  admin.is_master ? styles.masterBadge : styles.adminBadge
                }
              >
                {gradeLabel}
              </span>
            </span>
            <span className={styles.accountHint} aria-hidden="true">
              계정 수정
            </span>
          </Link>
        )}
        <button
          type="button"
          onClick={() => {
            void handleLogout();
          }}
          className={styles.logoutBtn}
        >
          로그아웃
        </button>
      </div>
    </header>
  );
}
