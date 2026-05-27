"use client";

/**
 * Story 10.5 — /admin/admins/permissions 등급 × 페이지 권한 매트릭스.
 *
 * - 행: 관리자 페이지(대시보드/고객관리/이상탐지/콘텐츠/RAG/재무/CS/수정요청/설정)
 * - 열: 관리자 등급 (운영 관리자 / 부운영자) — 마스터는 항상 전체 접근으로 매트릭스 제외
 * - 토글: 즉시 PATCH /api/v1/admin/grade-permissions
 *
 * 접근 권한:
 * - 조회: master / operator
 * - 수정: master 만 (operator 가 토글 시 403)
 */

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAdminSessionStore } from "@/stores/admin-session-store";
import {
  GradePermissionsApiError,
  fetchGradePermissionMatrix,
  patchGradePermission,
  type ConfigurableGrade,
  type GradePermissionMatrixResponse,
  type GradePermissionRow,
} from "@/features/admin-grade-permissions/api";
import styles from "./page.module.css";

const QUERY_KEY = ["admin-grade-permissions"] as const;

const GRADE_LABELS: Record<ConfigurableGrade, string> = {
  operator: "운영 관리자",
  sub_operator: "부운영자",
};

const GRADE_CHIP_CLASS: Record<ConfigurableGrade, string> = {
  operator: styles.gradeOperator,
  sub_operator: styles.gradeSub,
};

interface Toast {
  message: string;
  isError: boolean;
}

export default function AdminGradePermissionsPage() {
  const admin = useAdminSessionStore((s) => s.admin);
  const actorIsMaster = !!admin?.is_master;
  const queryClient = useQueryClient();

  const [toast, setToast] = useState<Toast | null>(null);
  // 토글 중인 셀(낙관적 UI). key = "${grade}|${route}"
  const [pendingCells, setPendingCells] = useState<Set<string>>(new Set());

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: QUERY_KEY,
    queryFn: fetchGradePermissionMatrix,
    staleTime: 10_000,
  });

  const patchMutation = useMutation({
    mutationFn: (payload: {
      admin_grade: ConfigurableGrade;
      page_route: string;
      allowed: boolean;
    }) => patchGradePermission(payload),
    onSuccess: (updated) => {
      // 캐시 갱신
      queryClient.setQueryData<GradePermissionMatrixResponse>(QUERY_KEY, (prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          rows: prev.rows.map((r) =>
            r.admin_grade === updated.admin_grade &&
            r.page_route === updated.page_route
              ? { ...r, allowed: updated.allowed }
              : r,
          ),
        };
      });
      showToast(
        `${GRADE_LABELS[updated.admin_grade]} · ${updated.page_route} → ${updated.allowed ? "허용" : "차단"}`,
      );
    },
    onError: (e, vars) => {
      if (e instanceof GradePermissionsApiError) {
        showToast(e.message, true);
      } else {
        showToast("권한 변경에 실패했습니다.", true);
      }
      // 실패 시 서버 상태로 재동기화
      queryClient.invalidateQueries({ queryKey: QUERY_KEY });
      // pending 해제
      const key = `${vars.admin_grade}|${vars.page_route}`;
      setPendingCells((prev) => {
        const next = new Set(prev);
        next.delete(key);
        return next;
      });
    },
    onSettled: (_data, _err, vars) => {
      const key = `${vars.admin_grade}|${vars.page_route}`;
      setPendingCells((prev) => {
        const next = new Set(prev);
        next.delete(key);
        return next;
      });
    },
  });

  function showToast(message: string, isError = false) {
    setToast({ message, isError });
    window.setTimeout(() => setToast(null), 2500);
  }

  function handleToggle(row: GradePermissionRow, nextAllowed: boolean) {
    if (!actorIsMaster) {
      showToast("권한 변경은 마스터만 가능합니다.", true);
      return;
    }
    const key = `${row.admin_grade}|${row.page_route}`;
    setPendingCells((prev) => new Set(prev).add(key));
    // 낙관적 업데이트
    queryClient.setQueryData<GradePermissionMatrixResponse>(QUERY_KEY, (prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        rows: prev.rows.map((r) =>
          r.admin_grade === row.admin_grade && r.page_route === row.page_route
            ? { ...r, allowed: nextAllowed }
            : r,
        ),
      };
    });
    patchMutation.mutate({
      admin_grade: row.admin_grade,
      page_route: row.page_route,
      allowed: nextAllowed,
    });
  }

  // (grade, route) → allowed 빠른 조회용 맵
  const cellMap = useMemo(() => {
    const m = new Map<string, GradePermissionRow>();
    (data?.rows ?? []).forEach((r) => {
      m.set(`${r.admin_grade}|${r.page_route}`, r);
    });
    return m;
  }, [data]);

  const pages = data?.pages ?? [];
  const grades: ConfigurableGrade[] = data?.grades ?? ["operator", "sub_operator"];

  return (
    <section className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>관리자 등급별 페이지 권한</h1>
        <p className={styles.caption}>
          각 관리자 등급이 접근할 수 있는 페이지를 설정합니다. 마스터는 설정과 무관하게 항상 모든 페이지에 접근 가능합니다.
        </p>
      </header>

      <div className={styles.notice}>
        <span className={styles.noticeDot} aria-hidden="true" />
        <span>
          토글을 끄면 해당 등급의 관리자는 그 페이지의 메뉴가 사이드바에서 보이지 않고, 직접 URL 로 접근해도 거절됩니다.
          {!actorIsMaster ? " 현재 등급에서는 매트릭스를 조회만 할 수 있습니다." : ""}
        </span>
      </div>

      <div className={styles.refreshRow}>
        <button
          type="button"
          className={styles.refreshBtn}
          onClick={() => refetch()}
          disabled={isLoading}
          data-testid="refresh-matrix"
        >
          새로고침
        </button>
      </div>

      {isError ? (
        <div className={styles.errorState}>권한 매트릭스를 불러오지 못했습니다.</div>
      ) : isLoading || !data ? (
        <div className={styles.emptyState}>불러오는 중...</div>
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">페이지</th>
                {grades.map((g) => (
                  <th key={g} scope="col" className={styles.toggleCell}>
                    <span className={`${styles.gradeChip} ${GRADE_CHIP_CLASS[g]}`}>
                      {GRADE_LABELS[g]}
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {pages.map((p) => (
                <tr key={p.page_route} data-testid={`row-${p.page_route}`}>
                  <td>
                    <div className={styles.routeCell}>
                      <span className={styles.routeLabel}>{p.label}</span>
                      <span className={styles.routePath}>{p.page_route}</span>
                    </div>
                  </td>
                  {grades.map((g) => {
                    const row = cellMap.get(`${g}|${p.page_route}`);
                    const allowed = !!row?.allowed;
                    const key = `${g}|${p.page_route}`;
                    const isPending = pendingCells.has(key);
                    return (
                      <td key={g} className={styles.toggleCell}>
                        <label className={styles.switch}>
                          <input
                            type="checkbox"
                            checked={allowed}
                            disabled={!actorIsMaster || isPending}
                            onChange={(e) =>
                              row && handleToggle(row, e.target.checked)
                            }
                            aria-label={`${GRADE_LABELS[g]} · ${p.label} 접근 ${allowed ? "허용" : "차단"}`}
                            data-testid={`toggle-${g}-${p.page_route}`}
                          />
                          <span className={styles.slider} aria-hidden="true" />
                        </label>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {toast ? (
        <div
          className={`${styles.toast} ${toast.isError ? styles.toastError : ""}`}
          role="status"
        >
          {toast.message}
        </div>
      ) : null}
    </section>
  );
}
