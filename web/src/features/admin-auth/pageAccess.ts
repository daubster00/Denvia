/**
 * Story 10.5 — 사이드바·URL 가드 공용 권한 헬퍼.
 *
 * 백엔드 ADMIN_PAGE_ROUTES (api/src/services/admin_grade_permission_service.py) 와 1:1 매핑한다.
 * 사이드바 children(예: /admin/synonyms, /admin/prompt) 은 부모 매트릭스 라우트로 묶인다.
 * /admin/admins/* 는 매트릭스 밖 — master·operator 전용 (grade-based).
 */

import type { AdminSessionUser } from "./api";

/** 매트릭스에 등록된 1차 라우트 — 백엔드 ADMIN_PAGE_ROUTES 와 동일 순서. */
export const ADMIN_MATRIX_ROUTES = [
  "/admin",
  "/admin/users",
  "/admin/anomaly",
  "/admin/content",
  "/admin/rag",
  "/admin/finance",
  "/admin/cs",
  "/admin/board",
  "/admin/qa-review",
  "/admin/alimtalk",
  "/admin/settings",
] as const;

export type AdminMatrixRoute = (typeof ADMIN_MATRIX_ROUTES)[number];

/**
 * 현재 pathname → 권한 매트릭스의 1차 라우트로 정규화.
 *
 * - 매트릭스 매핑이 있으면 해당 라우트
 * - /admin/admins/* → "admins" (별도 grade 가드)
 * - /admin/account, /admin/login, /admin/signup → "always" (모든 관리자 허용)
 * - 미상 → null (가드 시 차단)
 */
export type ResolvedRoute = AdminMatrixRoute | "admins" | "always" | null;

export function resolveAdminPageRoute(pathname: string): ResolvedRoute {
  if (pathname === "/admin" || pathname === "/admin/") return "/admin";

  // 별도 grade 가드 페이지
  if (pathname.startsWith("/admin/admins")) return "admins";
  if (
    pathname.startsWith("/admin/account") ||
    pathname.startsWith("/admin/login") ||
    pathname.startsWith("/admin/signup")
  ) {
    return "always";
  }

  // 대시보드 산하 (analytics, token-breakdown, budget)
  if (pathname.startsWith("/admin/dashboard")) return "/admin";

  // RAG 산하 (코드소스/동의어/프롬프트)
  if (
    pathname.startsWith("/admin/rag") ||
    pathname.startsWith("/admin/synonyms") ||
    pathname.startsWith("/admin/prompt")
  ) {
    return "/admin/rag";
  }

  // 부관리자 활동 리포트(급여 산정용 데이터) — 전체 열람 등급(master/operator)만.
  // /admin/qa-review 매트릭스보다 먼저 매칭해야 함(부관리자에게 노출되면 안 됨).
  if (pathname.startsWith("/admin/qa-review/activity")) return "admins";

  // 알림톡 관리(/admin/alimtalk) — 단일 페이지, children 없음
  if (pathname === "/admin/alimtalk" || pathname.startsWith("/admin/alimtalk/")) {
    return "/admin/alimtalk";
  }

  for (const route of ADMIN_MATRIX_ROUTES) {
    if (route === "/admin") continue;
    if (pathname === route || pathname.startsWith(`${route}/`)) return route;
  }
  return null;
}

/** 본 관리자가 주어진 pathname 에 접근 가능한지. */
export function canAccessAdminPath(
  pathname: string,
  admin: Pick<AdminSessionUser, "admin_grade" | "allowed_pages"> | null,
): boolean {
  if (!admin) return false;
  // master / 백필 누락(null) → 전체 허용
  if (admin.admin_grade === "master" || admin.admin_grade === null) return true;

  const resolved = resolveAdminPageRoute(pathname);
  if (resolved === null) return false;
  if (resolved === "always") return true;
  if (resolved === "admins") {
    return admin.admin_grade === "operator";
  }
  return admin.allowed_pages.includes(resolved);
}
