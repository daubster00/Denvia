"use client";

/**
 * Story 10.3 — /admin/admins 관리자 관리 페이지.
 *
 * - 목록: 전체 관리자 (master/operator/sub_operator/pending) — 필터 4종.
 * - 액션: 승인 / 차단 / 차단 해제 / 삭제 / 등급 변경. master 행은 액션 비활성.
 * - operator 로그인 시 master/다른 operator 행 액션 버튼 비활성 (백엔드도 가드).
 * - 자기 자신 액션 차단(본인 행에는 액션 버튼 미노출 — /admin/account 에서 본인 관리).
 *
 * CSS Modules, 좌측 정렬, max-width 1300px (메모: feedback_no_inline_css, feedback_admin_left_align).
 */

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAdminSessionStore } from "@/stores/admin-session-store";
import {
  AdminAccountsApiError,
  approveAdmin,
  blockAdmin,
  deleteAdmin,
  fetchAdminAccounts,
  patchAdminGrade,
  unblockAdmin,
  type AdminAccountItem,
  type AdminGrade,
  type AdminListFilter,
} from "@/features/admin-accounts/api";
import styles from "./page.module.css";

const FILTER_OPTIONS: { label: string; value: AdminListFilter }[] = [
  { label: "전체", value: "all" },
  { label: "승인대기", value: "pending" },
  { label: "활성", value: "active" },
  { label: "차단됨", value: "blocked" },
];

const QUERY_KEY = ["admin-accounts"] as const;

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

function _formatKstDateOnly(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString("ko-KR", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
}

function _gradeChipClass(grade: AdminGrade): string {
  switch (grade) {
    case "master":
      return styles.gradeMaster;
    case "operator":
      return styles.gradeOperator;
    case "sub_operator":
      return styles.gradeSub;
    case "pending":
    default:
      return styles.gradePending;
  }
}

/**
 * actor 가 target 에 대해 변경 액션을 수행할 수 있는지 판정.
 * 백엔드 가드(_guard_*) 와 동일한 규칙 — UI 사전 차단.
 */
function canActOn(
  actorIsMaster: boolean,
  actorIsOperator: boolean,
  actorId: number,
  target: AdminAccountItem,
): boolean {
  if (target.id === actorId) return false;
  if (target.admin_grade === "master") return false;
  if (actorIsOperator && target.admin_grade === "operator") return false;
  return actorIsMaster || actorIsOperator;
}

type ModalState =
  | { kind: "none" }
  | { kind: "approve"; target: AdminAccountItem }
  | { kind: "block"; target: AdminAccountItem }
  | { kind: "unblock"; target: AdminAccountItem }
  | { kind: "delete"; target: AdminAccountItem }
  | { kind: "grade"; target: AdminAccountItem };

interface Toast {
  message: string;
  isError: boolean;
}

export default function AdminAccountsPage() {
  const admin = useAdminSessionStore((s) => s.admin);
  const [filter, setFilter] = useState<AdminListFilter>("all");
  const [modal, setModal] = useState<ModalState>({ kind: "none" });
  const [toast, setToast] = useState<Toast | null>(null);

  const actorId = admin?.user_id ?? -1;
  const actorIsMaster = !!admin?.is_master;
  // is_master=false 인 활성 관리자는 일단 operator 로 취급.
  // sub_operator/pending 은 require_admin_grade('master','operator') 로 페이지 자체 접근 불가이므로
  // 이 페이지가 보인다는 사실 자체가 master 또는 operator 임을 의미한다.
  const actorIsOperator = !actorIsMaster;

  const queryClient = useQueryClient();

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: [...QUERY_KEY, filter],
    queryFn: () => fetchAdminAccounts(filter),
    staleTime: 10_000,
  });

  function showToast(message: string, isError = false) {
    setToast({ message, isError });
    window.setTimeout(() => setToast(null), 2500);
  }

  function handleError(e: unknown, fallback: string) {
    if (e instanceof AdminAccountsApiError) {
      showToast(e.message || fallback, true);
    } else if (e instanceof Error) {
      showToast(e.message || fallback, true);
    } else {
      showToast(fallback, true);
    }
  }

  function closeModal() {
    setModal({ kind: "none" });
  }

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: QUERY_KEY });
  }

  // 액션 mutation 들
  const approveMutation = useMutation({
    mutationFn: ({ id, grade }: { id: number; grade: "sub_operator" | "operator" }) =>
      approveAdmin(id, grade),
    onSuccess: () => {
      showToast("승인되었습니다.");
      invalidate();
      closeModal();
    },
    onError: (e) => handleError(e, "승인 처리에 실패했습니다."),
  });

  const blockMutation = useMutation({
    mutationFn: ({ id, blocked_until, reason }: { id: number; blocked_until: string; reason: string }) =>
      blockAdmin(id, { blocked_until, reason }),
    onSuccess: () => {
      showToast("차단되었습니다.");
      invalidate();
      closeModal();
    },
    onError: (e) => handleError(e, "차단 처리에 실패했습니다."),
  });

  const unblockMutation = useMutation({
    mutationFn: (id: number) => unblockAdmin(id),
    onSuccess: () => {
      showToast("차단을 해제했습니다.");
      invalidate();
      closeModal();
    },
    onError: (e) => handleError(e, "차단 해제에 실패했습니다."),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteAdmin(id),
    onSuccess: () => {
      showToast("삭제되었습니다.");
      invalidate();
      closeModal();
    },
    onError: (e) => handleError(e, "삭제에 실패했습니다."),
  });

  const gradeMutation = useMutation({
    mutationFn: ({ id, grade }: { id: number; grade: AdminGrade }) =>
      patchAdminGrade(id, grade),
    onSuccess: () => {
      showToast("등급을 변경했습니다.");
      invalidate();
      closeModal();
    },
    onError: (e) => handleError(e, "등급 변경에 실패했습니다."),
  });

  const items = useMemo(() => data?.items ?? [], [data]);

  return (
    <section className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>관리자 관리</h1>
        <p className={styles.caption}>
          관리자 가입 신청을 승인하고, 등급·차단·삭제를 관리합니다. 본인 계정은 /admin/account 에서 별도 관리하세요.
        </p>
      </header>

      <div className={styles.controls}>
        <div className={styles.filterRow} role="group" aria-label="상태 필터">
          {FILTER_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              className={filter === opt.value ? styles.filterBtnActive : styles.filterBtn}
              onClick={() => setFilter(opt.value)}
            >
              {opt.label}
            </button>
          ))}
        </div>
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
        <div className={styles.errorState}>관리자 목록을 불러오지 못했습니다.</div>
      ) : isLoading ? (
        <div className={styles.emptyState}>불러오는 중...</div>
      ) : items.length === 0 ? (
        <div className={styles.emptyState}>표시할 관리자가 없습니다.</div>
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>이메일</th>
                <th>등급</th>
                <th>휴대폰</th>
                <th>가입일자</th>
                <th>차단 상태</th>
                <th>액션</th>
              </tr>
            </thead>
            <tbody>
              {items.map((row) => {
                const canAct = canActOn(actorIsMaster, actorIsOperator, actorId, row);
                const isPending = row.admin_grade === "pending";
                const isBlocked =
                  !!row.admin_blocked_until &&
                  new Date(row.admin_blocked_until).getTime() > Date.now();
                return (
                  <tr key={row.id} data-testid={`admin-row-${row.id}`}>
                    <td>
                      {row.email}
                      {row.id === actorId ? <span className={styles.muted}> (본인)</span> : null}
                    </td>
                    <td>
                      <span className={`${styles.gradeChip} ${_gradeChipClass(row.admin_grade)}`}>
                        {row.grade_label}
                      </span>
                    </td>
                    <td>{row.phone_masked ?? <span className={styles.muted}>—</span>}</td>
                    <td>{_formatKstDateOnly(row.created_at)}</td>
                    <td>
                      {isBlocked ? (
                        <span className={styles.blockChip}>
                          차단 ~ {_formatKstDate(row.admin_blocked_until)}
                        </span>
                      ) : isPending ? (
                        <span className={styles.muted}>승인대기</span>
                      ) : (
                        <span className={styles.activeChip}>활성</span>
                      )}
                    </td>
                    <td>
                      <div className={styles.actionCell}>
                        {isPending ? (
                          <button
                            type="button"
                            className={styles.actionBtn}
                            disabled={!canAct}
                            data-testid={`btn-approve-${row.id}`}
                            onClick={() => setModal({ kind: "approve", target: row })}
                          >
                            승인
                          </button>
                        ) : null}
                        {!isPending && !isBlocked ? (
                          <button
                            type="button"
                            className={styles.actionBtn}
                            disabled={!canAct}
                            data-testid={`btn-block-${row.id}`}
                            onClick={() => setModal({ kind: "block", target: row })}
                          >
                            차단
                          </button>
                        ) : null}
                        {isBlocked ? (
                          <button
                            type="button"
                            className={styles.actionBtn}
                            disabled={!canAct}
                            data-testid={`btn-unblock-${row.id}`}
                            onClick={() => setModal({ kind: "unblock", target: row })}
                          >
                            차단 해제
                          </button>
                        ) : null}
                        {!isPending ? (
                          <button
                            type="button"
                            className={styles.actionBtn}
                            disabled={!canAct}
                            data-testid={`btn-grade-${row.id}`}
                            onClick={() => setModal({ kind: "grade", target: row })}
                          >
                            등급 변경
                          </button>
                        ) : null}
                        <button
                          type="button"
                          className={`${styles.actionBtn} ${styles.dangerBtn}`}
                          disabled={!canAct}
                          data-testid={`btn-delete-${row.id}`}
                          onClick={() => setModal({ kind: "delete", target: row })}
                        >
                          삭제
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {modal.kind === "approve" ? (
        <ApproveModal
          target={modal.target}
          actorIsMaster={actorIsMaster}
          onClose={closeModal}
          onSubmit={(grade) =>
            approveMutation.mutate({ id: modal.target.id, grade })
          }
          pending={approveMutation.isPending}
        />
      ) : null}

      {modal.kind === "block" ? (
        <BlockModal
          target={modal.target}
          onClose={closeModal}
          onSubmit={(payload) =>
            blockMutation.mutate({
              id: modal.target.id,
              blocked_until: payload.blocked_until,
              reason: payload.reason,
            })
          }
          pending={blockMutation.isPending}
        />
      ) : null}

      {modal.kind === "unblock" ? (
        <ConfirmModal
          title="차단을 해제하시겠습니까?"
          caption={`${modal.target.email} 계정의 일시 차단이 해제됩니다.`}
          confirmLabel="해제"
          onClose={closeModal}
          onConfirm={() => unblockMutation.mutate(modal.target.id)}
          pending={unblockMutation.isPending}
        />
      ) : null}

      {modal.kind === "delete" ? (
        <DeleteModal
          target={modal.target}
          onClose={closeModal}
          onSubmit={() => deleteMutation.mutate(modal.target.id)}
          pending={deleteMutation.isPending}
        />
      ) : null}

      {modal.kind === "grade" ? (
        <GradeChangeModal
          target={modal.target}
          actorIsMaster={actorIsMaster}
          onClose={closeModal}
          onSubmit={(grade) => gradeMutation.mutate({ id: modal.target.id, grade })}
          pending={gradeMutation.isPending}
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

// ── 모달 컴포넌트 ────────────────────────────────────────────────────────────

function ApproveModal({
  target,
  actorIsMaster,
  onClose,
  onSubmit,
  pending,
}: {
  target: AdminAccountItem;
  actorIsMaster: boolean;
  onClose: () => void;
  onSubmit: (grade: "sub_operator" | "operator") => void;
  pending: boolean;
}) {
  const [grade, setGrade] = useState<"sub_operator" | "operator">("sub_operator");
  return (
    <ModalShell onClose={onClose}>
      <h2 className={styles.modalTitle}>관리자 승인</h2>
      <p className={styles.modalCaption}>
        {target.email} — 어떤 등급으로 승인하시겠습니까?
      </p>
      <div className={styles.field}>
        <div className={styles.radioRow}>
          <label className={styles.radioLabel}>
            <input
              type="radio"
              name="approve-grade"
              checked={grade === "sub_operator"}
              onChange={() => setGrade("sub_operator")}
            />
            <span>부운영자</span>
          </label>
          <label className={styles.radioLabel}>
            <input
              type="radio"
              name="approve-grade"
              checked={grade === "operator"}
              disabled={!actorIsMaster}
              onChange={() => setGrade("operator")}
            />
            <span>운영 관리자{!actorIsMaster ? " (마스터 전용)" : ""}</span>
          </label>
        </div>
      </div>
      <div className={styles.modalActions}>
        <button type="button" className={styles.btnGhost} onClick={onClose} disabled={pending}>
          취소
        </button>
        <button
          type="button"
          className={styles.btnPrimary}
          onClick={() => onSubmit(grade)}
          disabled={pending}
          data-testid="approve-confirm"
        >
          승인
        </button>
      </div>
    </ModalShell>
  );
}

function BlockModal({
  target,
  onClose,
  onSubmit,
  pending,
}: {
  target: AdminAccountItem;
  onClose: () => void;
  onSubmit: (payload: { blocked_until: string; reason: string }) => void;
  pending: boolean;
}) {
  const defaultUntil = useMemo(() => {
    const d = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000);
    return d.toISOString().slice(0, 16); // datetime-local 입력 포맷 (로컬 시간 기준)
  }, []);
  const [until, setUntil] = useState<string>(defaultUntil);
  const [reason, setReason] = useState<string>("");
  const [error, setError] = useState<string>("");

  function handleSubmit() {
    setError("");
    if (!until) {
      setError("차단 만료 시각을 입력해주세요.");
      return;
    }
    const iso = new Date(until).toISOString();
    if (new Date(iso).getTime() <= Date.now()) {
      setError("만료 시각은 현재보다 이후여야 합니다.");
      return;
    }
    if (!reason.trim()) {
      setError("사유를 입력해주세요.");
      return;
    }
    onSubmit({ blocked_until: iso, reason: reason.trim() });
  }

  return (
    <ModalShell onClose={onClose}>
      <h2 className={styles.modalTitle}>관리자 차단</h2>
      <p className={styles.modalCaption}>
        {target.email} — 지정한 시각까지 로그인이 차단됩니다.
      </p>
      <label className={styles.field}>
        <span className={styles.fieldLabel}>차단 만료</span>
        <input
          type="datetime-local"
          className={styles.fieldInput}
          value={until}
          onChange={(e) => setUntil(e.target.value)}
        />
        <span className={styles.fieldHelp}>기본값: 7일 후</span>
      </label>
      <label className={styles.field}>
        <span className={styles.fieldLabel}>사유</span>
        <textarea
          className={styles.fieldTextarea}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="차단 사유를 입력해주세요."
        />
      </label>
      {error ? <span className={styles.fieldError}>{error}</span> : null}
      <div className={styles.modalActions}>
        <button type="button" className={styles.btnGhost} onClick={onClose} disabled={pending}>
          취소
        </button>
        <button
          type="button"
          className={styles.btnPrimary}
          onClick={handleSubmit}
          disabled={pending}
          data-testid="block-confirm"
        >
          차단
        </button>
      </div>
    </ModalShell>
  );
}

function ConfirmModal({
  title,
  caption,
  confirmLabel,
  onClose,
  onConfirm,
  pending,
}: {
  title: string;
  caption: string;
  confirmLabel: string;
  onClose: () => void;
  onConfirm: () => void;
  pending: boolean;
}) {
  return (
    <ModalShell onClose={onClose}>
      <h2 className={styles.modalTitle}>{title}</h2>
      <p className={styles.modalCaption}>{caption}</p>
      <div className={styles.modalActions}>
        <button type="button" className={styles.btnGhost} onClick={onClose} disabled={pending}>
          취소
        </button>
        <button
          type="button"
          className={styles.btnPrimary}
          onClick={onConfirm}
          disabled={pending}
          data-testid="confirm-yes"
        >
          {confirmLabel}
        </button>
      </div>
    </ModalShell>
  );
}

function DeleteModal({
  target,
  onClose,
  onSubmit,
  pending,
}: {
  target: AdminAccountItem;
  onClose: () => void;
  onSubmit: () => void;
  pending: boolean;
}) {
  const [emailInput, setEmailInput] = useState<string>("");
  const [confirmText, setConfirmText] = useState<string>("");
  const isReady =
    emailInput.trim().toLowerCase() === target.email.toLowerCase() &&
    confirmText.trim() === "삭제합니다";

  return (
    <ModalShell onClose={onClose}>
      <h2 className={styles.modalTitle}>관리자 삭제</h2>
      <p className={styles.modalCaption}>
        {target.email} 계정을 소프트 삭제합니다. 삭제된 계정은 동일 이메일로 재가입할 수 있습니다.
      </p>
      <label className={styles.field}>
        <span className={styles.fieldLabel}>이메일 재입력</span>
        <input
          type="email"
          className={styles.fieldInput}
          value={emailInput}
          onChange={(e) => setEmailInput(e.target.value)}
          placeholder={target.email}
        />
      </label>
      <label className={styles.field}>
        <span className={styles.fieldLabel}>확인 문구 "삭제합니다" 입력</span>
        <input
          type="text"
          className={styles.fieldInput}
          value={confirmText}
          onChange={(e) => setConfirmText(e.target.value)}
          placeholder="삭제합니다"
        />
      </label>
      <div className={styles.modalActions}>
        <button type="button" className={styles.btnGhost} onClick={onClose} disabled={pending}>
          취소
        </button>
        <button
          type="button"
          className={styles.btnDanger}
          onClick={onSubmit}
          disabled={!isReady || pending}
          data-testid="delete-confirm"
        >
          삭제
        </button>
      </div>
    </ModalShell>
  );
}

function GradeChangeModal({
  target,
  actorIsMaster,
  onClose,
  onSubmit,
  pending,
}: {
  target: AdminAccountItem;
  actorIsMaster: boolean;
  onClose: () => void;
  onSubmit: (grade: AdminGrade) => void;
  pending: boolean;
}) {
  const [grade, setGrade] = useState<AdminGrade>(
    target.admin_grade === "operator" ? "sub_operator" : "operator",
  );
  return (
    <ModalShell onClose={onClose}>
      <h2 className={styles.modalTitle}>등급 변경</h2>
      <p className={styles.modalCaption}>
        {target.email} — 현재 등급: <strong>{target.grade_label}</strong>
      </p>
      <div className={styles.field}>
        <div className={styles.radioRow}>
          <label className={styles.radioLabel}>
            <input
              type="radio"
              name="grade-new"
              checked={grade === "sub_operator"}
              onChange={() => setGrade("sub_operator")}
            />
            <span>부운영자</span>
          </label>
          <label className={styles.radioLabel}>
            <input
              type="radio"
              name="grade-new"
              checked={grade === "operator"}
              disabled={!actorIsMaster}
              onChange={() => setGrade("operator")}
            />
            <span>운영 관리자{!actorIsMaster ? " (마스터 전용)" : ""}</span>
          </label>
        </div>
      </div>
      <div className={styles.modalActions}>
        <button type="button" className={styles.btnGhost} onClick={onClose} disabled={pending}>
          취소
        </button>
        <button
          type="button"
          className={styles.btnPrimary}
          onClick={() => onSubmit(grade)}
          disabled={pending || grade === target.admin_grade}
          data-testid="grade-confirm"
        >
          변경
        </button>
      </div>
    </ModalShell>
  );
}

function ModalShell({
  children,
  onClose,
}: {
  children: React.ReactNode;
  onClose: () => void;
}) {
  return (
    <div
      className={styles.modalBackdrop}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      role="dialog"
      aria-modal="true"
    >
      <div className={styles.modal}>{children}</div>
    </div>
  );
}
