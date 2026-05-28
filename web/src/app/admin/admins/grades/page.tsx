"use client";

/**
 * /admin/admins/grades — 관리자 등급 관리 페이지.
 *
 * - 내장 4종(master/operator/sub_operator/pending)은 잠금(삭제·라벨변경 불가).
 * - 운영자가 새 등급을 추가하면 이 페이지·관리자 목록 등급 변경 모달·권한 매트릭스에 즉시 노출.
 * - 삭제는 해당 등급 사용자 0명일 때만. 사용 중이면 409 토스트로 안내.
 *
 * 좌측 정렬, max-width 1300px, CSS Modules (메모: feedback_no_inline_css, feedback_admin_left_align).
 */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AdminGradesApiError,
  createAdminGrade,
  deleteAdminGrade,
  fetchAdminGrades,
  type AdminGradeItem,
} from "@/features/admin-grades/api";
import styles from "./page.module.css";

const QUERY_KEY = ["admin-grades"] as const;

interface Toast {
  message: string;
  isError: boolean;
}

function _formatKstDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString("ko-KR", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function AdminGradesPage() {
  const queryClient = useQueryClient();
  const [label, setLabel] = useState<string>("");
  const [toast, setToast] = useState<Toast | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<AdminGradeItem | null>(null);

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: QUERY_KEY,
    queryFn: fetchAdminGrades,
    staleTime: 10_000,
  });

  function showToast(message: string, isError = false) {
    setToast({ message, isError });
    window.setTimeout(() => setToast(null), 2500);
  }

  function handleError(e: unknown, fallback: string) {
    if (e instanceof AdminGradesApiError) {
      showToast(e.message || fallback, true);
    } else if (e instanceof Error) {
      showToast(e.message || fallback, true);
    } else {
      showToast(fallback, true);
    }
  }

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: QUERY_KEY });
    // 관리자 목록의 등급 변경 모달도 캐시 사용 — 함께 무효화.
    queryClient.invalidateQueries({ queryKey: ["admin-grades"] });
    queryClient.invalidateQueries({ queryKey: ["admin-grade-permissions"] });
  }

  const createMutation = useMutation({
    mutationFn: (newLabel: string) => createAdminGrade(newLabel),
    onSuccess: (item) => {
      showToast(`"${item.label}" 등급을 추가했습니다.`);
      setLabel("");
      invalidate();
    },
    onError: (e) => handleError(e, "등급 추가에 실패했습니다."),
  });

  const deleteMutation = useMutation({
    mutationFn: (code: string) => deleteAdminGrade(code),
    onSuccess: () => {
      showToast("등급을 삭제했습니다.");
      setConfirmDelete(null);
      invalidate();
    },
    onError: (e) => handleError(e, "등급 삭제에 실패했습니다."),
  });

  function handleCreate() {
    const trimmed = label.trim();
    if (!trimmed) {
      showToast("등급 이름을 입력해주세요.", true);
      return;
    }
    createMutation.mutate(trimmed);
  }

  const items = data?.items ?? [];

  return (
    <section className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>관리자 등급 관리</h1>
        <p className={styles.caption}>
          새 관리자 등급을 추가하고 삭제합니다. 추가된 등급은 관리자 목록의 등급 변경과
          권한 관리 매트릭스에 자동으로 반영됩니다. 운영 관리자와 승인 대기는 시스템
          내장 등급이라 수정·삭제할 수 없습니다.
        </p>
      </header>

      <div className={styles.addBox}>
        <div className={styles.addRow}>
          <label htmlFor="grade-label" className={styles.addLabel}>
            등급 이름
          </label>
          <input
            id="grade-label"
            type="text"
            className={styles.addInput}
            placeholder="예: 회계 담당, 마케팅 매니저"
            value={label}
            maxLength={32}
            onChange={(e) => setLabel(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleCreate();
            }}
            disabled={createMutation.isPending}
            data-testid="grade-label-input"
          />
          <button
            type="button"
            className={styles.addBtn}
            onClick={handleCreate}
            disabled={createMutation.isPending || label.trim().length === 0}
            data-testid="grade-add-btn"
          >
            추가
          </button>
        </div>
        <p className={styles.addHelp}>
          1~32자. 같은 이름이나 예약된 이름(운영 관리자·승인 대기)은 사용할 수 없습니다.
          추가된 등급은 기본적으로 모든 페이지 접근이 차단되며, 권한 관리에서 페이지별로 켜주세요.
        </p>
      </div>

      <div className={styles.refreshRow}>
        <button
          type="button"
          className={styles.refreshBtn}
          onClick={() => refetch()}
          disabled={isLoading}
        >
          새로고침
        </button>
      </div>

      {isError ? (
        <div className={styles.errorState}>등급 목록을 불러오지 못했습니다.</div>
      ) : isLoading ? (
        <div className={styles.emptyState}>불러오는 중...</div>
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>등급 이름</th>
                <th>구분</th>
                <th>사용 중인 관리자 수</th>
                <th>생성일자</th>
                <th>액션</th>
              </tr>
            </thead>
            <tbody>
              {items.map((row) => (
                <tr key={row.code} data-testid={`grade-row-${row.code}`}>
                  <td>
                    <span className={styles.gradeLabel}>{row.label}</span>
                  </td>
                  <td>
                    {row.is_builtin ? (
                      <span className={styles.builtinChip}>내장</span>
                    ) : (
                      <span className={styles.customChip}>커스텀</span>
                    )}
                  </td>
                  <td>{row.user_count.toLocaleString()}명</td>
                  <td>{_formatKstDate(row.created_at)}</td>
                  <td>
                    {row.is_builtin ? (
                      <span className={styles.muted}>잠금</span>
                    ) : (
                      <button
                        type="button"
                        className={`${styles.actionBtn} ${styles.dangerBtn}`}
                        onClick={() => setConfirmDelete(row)}
                        data-testid={`grade-delete-${row.code}`}
                      >
                        삭제
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {confirmDelete ? (
        <DeleteConfirmModal
          target={confirmDelete}
          onClose={() => setConfirmDelete(null)}
          onConfirm={() => deleteMutation.mutate(confirmDelete.code)}
          pending={deleteMutation.isPending}
        />
      ) : null}

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

function DeleteConfirmModal({
  target,
  onClose,
  onConfirm,
  pending,
}: {
  target: AdminGradeItem;
  onClose: () => void;
  onConfirm: () => void;
  pending: boolean;
}) {
  const blocked = target.user_count > 0;
  return (
    <div
      className={styles.modalBackdrop}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      role="dialog"
      aria-modal="true"
    >
      <div className={styles.modal}>
        <h2 className={styles.modalTitle}>등급 삭제</h2>
        <p className={styles.modalCaption}>
          &quot;{target.label}&quot; 등급을 삭제합니다.
          {blocked
            ? ` 이 등급을 사용 중인 관리자가 ${target.user_count}명 있어 먼저 등급을 변경한 뒤 삭제해야 합니다.`
            : " 권한 매트릭스의 해당 등급 행도 함께 사라집니다."}
        </p>
        <div className={styles.modalActions}>
          <button
            type="button"
            className={styles.btnGhost}
            onClick={onClose}
            disabled={pending}
          >
            취소
          </button>
          <button
            type="button"
            className={styles.btnDanger}
            onClick={onConfirm}
            disabled={pending || blocked}
            data-testid="grade-delete-confirm"
          >
            삭제
          </button>
        </div>
      </div>
    </div>
  );
}
