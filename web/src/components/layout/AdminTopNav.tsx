"use client";

import { useSessionStore } from "@/stores/session-store";
import { LogoLink } from "@/components/brand/LogoLink";
import styles from "./AdminTopNav.module.css";

export function AdminTopNav() {
  const user = useSessionStore((s) => s.user);

  return (
    <header className={styles.header}>
      <LogoLink />

      <div className={styles.right}>
        {user && <span className={styles.email}>{user.email}</span>}
        <span className={styles.adminBadge}>관리자</span>
      </div>
    </header>
  );
}
