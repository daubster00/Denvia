"use client";

import { useEffect } from "react";
import { useRouter, usePathname } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { adminFetchMe } from "@/features/admin-auth/api";
import { canAccessAdminPath } from "@/features/admin-auth/pageAccess";
import { useAdminSessionStore } from "@/stores/admin-session-store";
import { fetchRagStatus } from "@/features/admin-rag/api/knowledge";
import { useAdminEventsSSE } from "@/features/admin-dashboard/hooks/useAdminEventsSSE";
import { useAdminEventsStore } from "@/stores/admin-events-store";
import { RebuildBanner } from "@/features/admin-rag/components/RebuildBanner";
import { AdminSidebar } from "@/components/layout/AdminSidebar";
import { AdminTopNav } from "@/components/layout/AdminTopNav";
import styles from "./admin.module.css";

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();

  // /admin/login, /admin/signup 페이지는 이 레이아웃의 인증 가드를 통과시키지 않고 그대로 렌더 — 무한 리다이렉트 방지.
  // 사이드바·탑네비·SSE 같은 admin 셸 요소도 비로그인 화면에는 불필요하므로 children만 반환한다.
  if (pathname === "/admin/login" || pathname === "/admin/signup") {
    return <>{children}</>;
  }

  return <AdminAuthenticatedShell pathname={pathname}>{children}</AdminAuthenticatedShell>;
}

function AdminAuthenticatedShell({
  children,
  pathname,
}: {
  children: React.ReactNode;
  pathname: string | null;
}) {
  const router = useRouter();
  const setAdmin = useAdminSessionStore((s) => s.setAdmin);
  const hideRebuildBanner = pathname?.startsWith("/admin/rag") ?? false;

  const { data: admin, isLoading, isError } = useQuery({
    queryKey: ["admin-session"],
    queryFn: adminFetchMe,
    retry: false,
  });

  const queryClient = useQueryClient();

  useEffect(() => {
    if (admin) {
      setAdmin(admin);
    }
  }, [admin, setAdmin]);

  // 관리자 페이지 내 이동마다 세션 재확인 — 백엔드 SessionRefreshMiddleware 가 쿠키 TTL 을 연장하여
  // 활동 중에는 1시간 만료가 무한 연장된다. 만료된 경우엔 401 → adminApiFetch 가 /admin/login 으로 리다이렉트.
  useEffect(() => {
    if (!pathname) return;
    queryClient.invalidateQueries({ queryKey: ["admin-session"] });
  }, [pathname, queryClient]);

  useAdminEventsSSE();

  const { data: ragStatus } = useQuery({
    queryKey: ["admin-rag-status"],
    queryFn: fetchRagStatus,
    staleTime: 30_000,
    // active rebuild 중에는 5초 폴링 — SSE 연결이 끊겨도 완료 상태를 감지
    refetchInterval: (query) => query.state.data?.active_rebuild ? 5_000 : false,
    enabled: !!admin,
  });

  const { rebuildProgress, activeJobId, lastCompletedJobId, setActiveJobId, setRebuildProgress, setLastCompletedJobId } = useAdminEventsStore();

  useEffect(() => {
    if (!ragStatus) return;

    if (ragStatus.active_rebuild) {
      // 재빌드 진행 중 — SSE가 없거나 아직 progress가 없을 때 DB 값으로 초기화
      if (!rebuildProgress && ragStatus.active_rebuild.job_id !== lastCompletedJobId) {
        setActiveJobId(ragStatus.active_rebuild.job_id);
        setRebuildProgress({
          type: "rag_rebuild_progress",
          job_id: ragStatus.active_rebuild.job_id,
          progress: ragStatus.active_rebuild.progress_percent,
          stage: ragStatus.active_rebuild.stage ?? "queued",
        });
      }
    } else if (rebuildProgress && activeJobId) {
      // 폴링으로 완료 감지 — SSE 이벤트를 놓쳤을 때 fallback
      setLastCompletedJobId(activeJobId);
      setRebuildProgress(null);
      setActiveJobId(null);
      queryClient.invalidateQueries({ queryKey: ["admin-rag-status"] });
      queryClient.invalidateQueries({ queryKey: ["admin-rag-knowledge"] });
    }
  }, [ragStatus, rebuildProgress, activeJobId, lastCompletedJobId, setActiveJobId, setRebuildProgress, setLastCompletedJobId, queryClient]);

  useEffect(() => {
    if (!isLoading && (isError || !admin)) {
      router.replace("/admin/login");
    }
  }, [admin, isLoading, isError, router]);

  if (isLoading || !admin) {
    return null;
  }

  // Story 10.5 — URL 직접 접근 가드. 권한 없는 페이지는 children 대신 안내 화면을 렌더.
  // 사이드바·TopNav 는 그대로 노출해서 다른 페이지로 이동할 수 있게 한다.
  const allowedHere = pathname ? canAccessAdminPath(pathname, admin) : false;

  return (
    <div className={styles.adminShell}>
      <AdminSidebar />
      <div className={styles.adminBody}>
        <AdminTopNav />
        {!hideRebuildBanner && <RebuildBanner />}
        <main id="admin-main" tabIndex={-1} className={styles.adminMain}>
          {allowedHere ? children : <AdminAccessDenied />}
        </main>
      </div>
    </div>
  );
}

function AdminAccessDenied() {
  return (
    <div className={styles.forbiddenWrap}>
      <div className={styles.forbiddenCard}>
        <h2 className={styles.forbiddenTitle}>접근 권한이 없습니다</h2>
        <p className={styles.forbiddenBody}>
          이 페이지에 접근할 수 있는 권한이 부여되어 있지 않습니다.
          <br />
          권한이 필요하다면 마스터 관리자에게 문의해 주세요.
        </p>
        <Link href="/admin" className={styles.forbiddenAction}>
          대시보드로 돌아가기
        </Link>
      </div>
    </div>
  );
}
