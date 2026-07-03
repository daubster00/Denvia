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
      // 관리자 데이터 캐시 전체 제거 — 같은 브라우저에서 다른 등급 계정으로
      // 다시 로그인했을 때 이전 계정의 캐시(예: 질의응답 검토 목록 — 부운영자
      // 조회기간 제한이 걸리지 않은 운영자 응답)가 남아 노출되는 것을 막는다.
      queryClient.clear();
      router.replace("/admin/login");
    }
  };

  const gradeLabel = admin?.is_master ? "마스터" : "관리자";

  // 마스터는 무조건 노출, 그 외 등급은 권한 매트릭스의 /admin/feature/openai-warmup 가 켜져 있어야 노출.
  const canSeeWarmup =
    !!admin &&
    (admin.is_master ||
      (admin.allowed_pages?.includes("/admin/feature/openai-warmup") ?? false));

  return (
    <header className={styles.header}>
      <LogoLink href="/admin" ariaLabel="관리자 대시보드" />

      <div className={styles.right}>
        <AdminWarmupToggle canSee={canSeeWarmup} />
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
