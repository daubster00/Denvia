"use client";

import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { useAdminSessionStore } from "@/stores/admin-session-store";
import { adminLogout } from "@/features/admin-auth/api";
import { LogoLink } from "@/components/brand/LogoLink";
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

  return (
    <header className={styles.header}>
      <LogoLink />

      <div className={styles.right}>
        {admin && <span className={styles.email}>{admin.email}</span>}
        <span className={styles.adminBadge}>관리자</span>
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
