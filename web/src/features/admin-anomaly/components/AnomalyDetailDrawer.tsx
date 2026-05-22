"use client";

import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  fetchAnomalyDetail,
  saveAnomalyMemo,
  type AnomalyDetailResponse,
  type AnomalyType,
} from "@/features/admin-anomaly/api/anomaly";
import { formatAnomalyType } from "@/features/admin-users/labels";
import { clearAnomalyThrottle } from "@/features/admin-users/api/users";
import { useUpdatePermission } from "@/features/admin-users/hooks/useUpdatePermission";
import { useToastStore } from "@/stores/toast-store";
import { AnomalyStatusBadge } from "./AnomalyStatusBadge";
import styles from "./AnomalyDetailDrawer.module.css";

interface Props {
  anomalyId: number;
  onClose: () => void;
}

const KST_FORMAT = new Intl.DateTimeFormat("ko-KR", {
  timeZone: "Asia/Seoul",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

function formatDateTime(value: string | null): string {
  if (!value) return "—";
  try {
    return KST_FORMAT.format(new Date(value));
  } catch {
    return value;
  }
}

const DETECTION_CRITERIA: Record<AnomalyType, string> = {
  login_brute_force:
    "동일 계정에 대해 짧은 시간 내 비밀번호 오류가 연속 누적되면 탐지됩니다.",
  concurrent_ip_login:
    "동일 IP에서 10분 이내 서로 다른 3개 이상의 계정 로그인이 성공하면 탐지됩니다.",
  repeated_question:
    "동일·유사 질문을 짧은 시간 내 반복적으로 던질 때 탐지됩니다.",
  recovery_abuse:
    "비밀번호 재설정·아이디 찾기 요청을 비정상적으로 반복할 때 탐지됩니다.",
  rapid_followup_questions:
    "직전 답변이 끝난 뒤 3초 이내에 새 질문을 연속 3회 던지면 자동으로 탐지됩니다. " +
    "시스템이 즉시 자동 쿨다운(질문 속도 제한)을 적용합니다.",
};

const LOGIN_ANOMALY_TYPES: AnomalyType[] = [
  "login_brute_force",
  "concurrent_ip_login",
];

function isLoginAnomaly(type: AnomalyType): boolean {
  return LOGIN_ANOMALY_TYPES.includes(type);
}

function deriveBlockState(detail: AnomalyDetailResponse): {
  isFullBlocked: boolean;
  isQuestionBlocked: boolean;
} {
  const now = Date.now();
  const isFullBlocked = detail.user_subscription_status === "blocked";
  const qbUntil = detail.user_question_blocked_until
    ? new Date(detail.user_question_blocked_until).getTime()
    : null;
  const isQuestionBlocked = qbUntil !== null && qbUntil > now;
  return { isFullBlocked, isQuestionBlocked };
}

export function AnomalyDetailDrawer({ anomalyId, onClose }: Props) {
  const qc = useQueryClient();
  const showToast = useToastStore((s) => s.show);
  const updatePermission = useUpdatePermission();

  const [detail, setDetail] = useState<AnomalyDetailResponse | null>(null);
  const [memo, setMemo] = useState("");
  const [savingMemo, setSavingMemo] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [actionPending, setActionPending] = useState(false);

  async function reload() {
    setIsLoading(true);
    try {
      const data = await fetchAnomalyDetail(anomalyId);
      setDetail(data);
      setMemo(data.admin_memo ?? "");
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "상세를 불러오지 못했습니다.";
      showToast(message);
      onClose();
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [anomalyId]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function handleSaveMemo() {
    setSavingMemo(true);
    try {
      const updated = await saveAnomalyMemo(anomalyId, memo);
      setDetail(updated);
      setMemo(updated.admin_memo ?? "");
      showToast("메모가 저장되었습니다.");
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "메모 저장에 실패했습니다.";
      showToast(message);
    } finally {
      setSavingMemo(false);
    }
  }

  async function handleClearThrottle() {
    if (!detail?.target_user_id) return;
    const ok = window.confirm(
      "쿨다운(자동 속도 제한)을 해제하시겠습니까? 사용자가 즉시 다시 질의할 수 있습니다.",
    );
    if (!ok) return;
    setActionPending(true);
    try {
      await clearAnomalyThrottle(detail.target_user_id);
      await qc.invalidateQueries({ queryKey: ["admin", "anomaly"] });
      showToast("자동 제한이 해제되었습니다.");
      await reload();
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "자동 제한 해제에 실패했습니다.";
      showToast(message);
    } finally {
      setActionPending(false);
    }
  }

  async function handleBlock(durationHours: number | null) {
    if (!detail?.target_user_id) {
      showToast("IP 기반 이벤트는 사용자 차단을 적용할 수 없습니다.");
      return;
    }
    const label =
      durationHours === null
        ? "영구 차단"
        : durationHours === 24
          ? "24시간 차단"
          : "7일 차단";
    const scope = isLoginAnomaly(detail.type) ? "all" : "question_only";
    const scopeNote =
      scope === "question_only"
        ? "\n(질문만 차단됩니다. 로그인 등 다른 활동은 가능합니다.)"
        : "";
    const ok = window.confirm(`${label} 처리하시겠습니까?${scopeNote}`);
    if (!ok) return;
    setActionPending(true);
    try {
      await updatePermission.mutateAsync({
        userId: detail.target_user_id,
        payload: {
          block_action: {
            duration_hours: durationHours,
            reason: `이상행동 탐지 (${formatAnomalyType(detail.type)})`,
            anomaly_id: detail.id,
            scope,
          },
        },
      });
      await qc.invalidateQueries({ queryKey: ["admin", "anomaly"] });
      showToast(`${label} 처리되었습니다.`);
      await reload();
    } catch {
      showToast("차단 처리에 실패했습니다. 다시 시도해주세요.");
    } finally {
      setActionPending(false);
    }
  }

  async function handleUnblock() {
    if (!detail?.target_user_id) return;
    const ok = window.confirm(
      "차단을 해제하시겠습니까? 사용자가 즉시 다시 이용할 수 있습니다.",
    );
    if (!ok) return;
    setActionPending(true);
    try {
      await updatePermission.mutateAsync({
        userId: detail.target_user_id,
        payload: { unblock: true },
      });
      await qc.invalidateQueries({ queryKey: ["admin", "anomaly"] });
      showToast("차단이 해제되었습니다.");
      await reload();
    } catch (err) {
      const code =
        err && typeof err === "object" && "code" in err
          ? (err as { code: string }).code
          : undefined;
      if (code === "UNBLOCK_TARGET_NOT_BLOCKED") {
        showToast("이미 차단이 해제된 사용자입니다.");
      } else {
        showToast("차단 해제에 실패했습니다. 다시 시도해주세요.");
      }
    } finally {
      setActionPending(false);
    }
  }

  function handleOverlayClick(e: React.MouseEvent) {
    if (e.target === e.currentTarget) onClose();
  }

  return (
    <div
      className={styles.overlay}
      onClick={handleOverlayClick}
      role="dialog"
      aria-modal="true"
    >
      <aside className={styles.drawer}>
        <header className={styles.header}>
          <h2 className={styles.title}>이상탐지 상세</h2>
          <button
            type="button"
            className={styles.closeButton}
            onClick={onClose}
            aria-label="닫기"
          >
            ×
          </button>
        </header>

        {isLoading || !detail ? (
          <div className={styles.loadingBox}>불러오는 중…</div>
        ) : (
          <div className={styles.body}>
            <div className={styles.fieldGrid}>
              <span className={styles.label}>탐지유형</span>
              <span className={styles.value}>{formatAnomalyType(detail.type)}</span>

              <span className={styles.label}>탐지일시</span>
              <span className={styles.value}>{formatDateTime(detail.created_at)}</span>

              <span className={styles.label}>대상 사용자</span>
              <span className={styles.value}>
                {detail.target_user_id ? (
                  <a
                    href={`/admin/users/${detail.target_user_id}`}
                    style={{ color: "var(--color-brand, #6366f1)", textDecoration: "none" }}
                  >
                    {detail.target_user_email_masked ?? `#${detail.target_user_id}`}
                  </a>
                ) : (
                  "—"
                )}
              </span>

              <span className={styles.label}>IP 주소</span>
              <span className={styles.value}>{detail.ip ?? "—"}</span>

              <span className={styles.label}>상태</span>
              <span className={styles.value}>
                <AnomalyStatusBadge status={detail.status} />
              </span>

              <span className={styles.label}>자동조치</span>
              <span className={styles.value}>
                {detail.auto_actioned ? "적용됨 (시스템 자동)" : "없음"}
              </span>

              <span className={styles.label}>누적 탐지횟수</span>
              <span className={styles.value}>{detail.occurrence_count}회</span>

              <span className={styles.label}>최근 탐지일시</span>
              <span className={styles.value}>
                {formatDateTime(detail.last_occurred_at)}
              </span>
            </div>

            <div className={styles.criterionBox}>
              <div className={styles.criterionTitle}>탐지기준</div>
              <div>{DETECTION_CRITERIA[detail.type]}</div>
            </div>

            <div className={styles.memoSection}>
              <label htmlFor="anomaly-memo" className={styles.memoLabel}>
                메모
              </label>
              <textarea
                id="anomaly-memo"
                className={styles.memoTextarea}
                value={memo}
                onChange={(e) => setMemo(e.target.value)}
                maxLength={2000}
                placeholder="이 이벤트에 대한 메모를 남길 수 있습니다."
              />
              <button
                type="button"
                className={styles.saveButton}
                onClick={handleSaveMemo}
                disabled={savingMemo}
              >
                {savingMemo ? "저장 중…" : "저장"}
              </button>
            </div>

            {detail.target_user_id ? (
              <div className={styles.actionSection}>
                <div className={styles.actionGroup}>
                  <div className={styles.actionTitle}>자동 제한 조치</div>
                  {detail.user_anomaly_throttled_at ? (
                    <div className={styles.actionRow}>
                      <button
                        type="button"
                        className={styles.unblockButton}
                        onClick={handleClearThrottle}
                        disabled={actionPending}
                      >
                        자동제한 해제
                      </button>
                    </div>
                  ) : (
                    <div className={styles.disabledHint}>
                      현재 자동 제한이 적용되어 있지 않습니다.
                    </div>
                  )}
                </div>

                <div className={styles.actionGroup}>
                  <div className={styles.actionTitle}>
                    차단 조치{" "}
                    {!isLoginAnomaly(detail.type) ? (
                      <span className={styles.disabledHint}>
                        (질문만 차단됩니다)
                      </span>
                    ) : null}
                  </div>
                  {(() => {
                    const { isFullBlocked, isQuestionBlocked } =
                      deriveBlockState(detail);
                    const blockedNow = isFullBlocked || isQuestionBlocked;
                    if (blockedNow) {
                      return (
                        <div className={styles.actionRow}>
                          <button
                            type="button"
                            className={styles.unblockButton}
                            onClick={handleUnblock}
                            disabled={actionPending}
                          >
                            차단 해제
                          </button>
                        </div>
                      );
                    }
                    return (
                      <div className={styles.actionRow}>
                        <button
                          type="button"
                          className={styles.actionButton}
                          onClick={() => handleBlock(24)}
                          disabled={actionPending}
                        >
                          24시간 차단
                        </button>
                        <button
                          type="button"
                          className={styles.actionButton}
                          onClick={() => handleBlock(24 * 7)}
                          disabled={actionPending}
                        >
                          7일 차단
                        </button>
                        <button
                          type="button"
                          className={styles.actionButton}
                          onClick={() => handleBlock(null)}
                          disabled={actionPending}
                        >
                          영구 차단
                        </button>
                      </div>
                    );
                  })()}
                </div>
              </div>
            ) : (
              <div className={styles.disabledHint}>
                IP 기반 이벤트는 사용자 단위 조치를 적용할 수 없습니다.
              </div>
            )}
          </div>
        )}
      </aside>
    </div>
  );
}
