"use client";

import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  clearLoginLockout,
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
    "비밀번호를 연속 3회 틀리면 1차 탐지(노란색) + 10분간 계정이 잠깁니다. " +
    "10분 후 1회 재시도가 가능하며, 그마저 실패하면 2차 탐지(빨간색)가 발생하고 " +
    "비밀번호 찾기로 재설정할 때까지 로그인이 차단됩니다.",
  concurrent_ip_login:
    "동일 IP에서 10분 이내 서로 다른 3개 이상의 계정 로그인이 성공하면 탐지됩니다.",
  repeated_question:
    "완전히 동일한 텍스트의 질문을 연속 3회 던지면 자동으로 탐지됩니다. " +
    "시스템이 즉시 자동 쿨다운(질문 속도 제한)을 적용합니다.",
  recovery_abuse:
    "비밀번호 재설정·아이디 찾기 요청을 비정상적으로 반복할 때 탐지됩니다.",
  rapid_followup_questions:
    "직전 답변이 끝난 뒤 3초 이내에 새 질문을 연속 3회 던지면 자동으로 탐지됩니다. " +
    "시스템이 즉시 자동 쿨다운(질문 속도 제한)을 적용합니다.",
  sms_abuse:
    "동일 휴대폰 번호로 1시간 이내 SMS 인증 요청이 10회 이상 발생하면 탐지됩니다. " +
    "시스템이 즉시 해당 번호를 24시간 자동 차단합니다.",
};

/**
 * 상세 응답에서 "지금" 차단/자동제한 활성 여부를 도출. 리스트의 user_blocked_now /
 * user_auto_throttled_now 와 동일 규칙(서버 사이드 계산을 클라이언트에서 재현).
 */
function deriveActiveState(detail: AnomalyDetailResponse): {
  blockedNow: boolean;
  throttledNow: boolean;
} {
  const now = Date.now();
  const parse = (iso: string | null): number | null =>
    iso ? new Date(iso).getTime() : null;

  const bu = parse(detail.user_blocked_until);
  const blockedNow =
    detail.user_subscription_status === "blocked" ||
    (bu !== null && bu > now);

  let throttledNow = detail.user_anomaly_throttled_at !== null;
  if (detail.type === "login_brute_force") {
    const lbf = parse(detail.login_auto_lockout_until);
    if (detail.login_hard_locked || (lbf !== null && lbf > now)) {
      throttledNow = true;
    }
  }

  return { blockedNow, throttledNow };
}

/** login_brute_force 탐지의 단계(1/2) 를 details 에서 안전하게 추출. */
function loginBruteForceStage(detail: AnomalyDetailResponse): 1 | 2 | null {
  if (detail.type !== "login_brute_force") return null;
  const stage = (detail.details as { stage?: unknown })?.stage;
  if (stage === 1) return 1;
  if (stage === 2) return 2;
  return null;
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

  async function handleClearLoginLockout() {
    if (!detail?.target_user_id) return;
    const ok = window.confirm(
      "로그인 자동 잠금을 해제하시겠습니까? 사용자가 즉시 로그인 재시도가 가능해집니다.",
    );
    if (!ok) return;
    setActionPending(true);
    try {
      await clearLoginLockout(detail.target_user_id);
      await qc.invalidateQueries({ queryKey: ["admin", "anomaly"] });
      showToast("로그인 자동 잠금이 해제되었습니다.");
      await reload();
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "로그인 잠금 해제에 실패했습니다.";
      showToast(message);
    } finally {
      setActionPending(false);
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
    const ok = window.confirm(`${label} 처리하시겠습니까?`);
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

              {(() => {
                const stage = loginBruteForceStage(detail);
                if (stage === null) return null;
                const cls =
                  stage === 2 ? styles.stageLabelRed : styles.stageLabelYellow;
                const label =
                  stage === 2
                    ? "2차 (재시도 또 실패 · 비번찾기 필수)"
                    : "1차 (3회 실패 · 10분 잠금)";
                return (
                  <>
                    <span className={styles.label}>단계</span>
                    <span className={styles.value}>
                      <span className={cls}>{label}</span>
                    </span>
                  </>
                );
              })()}

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
                {(() => {
                  const { blockedNow, throttledNow } = deriveActiveState(detail);
                  return (
                    <AnomalyStatusBadge
                      status={detail.status}
                      blockedNow={blockedNow}
                      throttledNow={throttledNow}
                    />
                  );
                })()}
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

            {detail.history.length > 1 ? (
              <div className={styles.historySection}>
                <div className={styles.historyTitle}>
                  내역 ({detail.history.length}회)
                </div>
                <ul className={styles.historyList}>
                  {detail.history.map((row) => (
                    <li
                      key={row.id}
                      className={
                        row.id === detail.id
                          ? styles.historyItemCurrent
                          : styles.historyItem
                      }
                      data-testid={`anomaly-history-${row.id}`}
                    >
                      <span className={styles.historyDate}>
                        {formatDateTime(row.created_at)}
                      </span>
                      <span className={styles.historyMeta}>
                        {/*
                         * history row 는 과거 시점 기록이라 "지금" 활성 상태를 알 수 없다.
                         * 현재 row 만 사용자 상태를 동봉해 표시하고, 그 외 과거 row 는
                         * 이벤트 자체의 status(new/reviewed/actioned/unblocked) 기반 라벨로 표시.
                         */}
                        {row.id === detail.id
                          ? (() => {
                              const { blockedNow, throttledNow } =
                                deriveActiveState(detail);
                              return (
                                <AnomalyStatusBadge
                                  status={row.status}
                                  blockedNow={blockedNow}
                                  throttledNow={throttledNow}
                                />
                              );
                            })()
                          : (
                            <AnomalyStatusBadge status={row.status} />
                          )}
                        {row.ip ? (
                          <span className={styles.historyIp}>{row.ip}</span>
                        ) : null}
                        {row.id === detail.id ? (
                          <span className={styles.historyCurrentTag}>
                            현재
                          </span>
                        ) : null}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

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
                  {(() => {
                    // login_brute_force 는 Redis 락아웃, 그 외는 users.anomaly_throttled_at 기반.
                    // 두 종류 모두 이 한 섹션에서 통합 표시·해제한다.
                    if (detail.type === "login_brute_force") {
                      const hardLocked = detail.login_hard_locked;
                      const lockoutUntilRaw = detail.login_auto_lockout_until;
                      const lockoutUntilMs = lockoutUntilRaw
                        ? new Date(lockoutUntilRaw).getTime()
                        : null;
                      const lockoutActive =
                        lockoutUntilMs !== null && lockoutUntilMs > Date.now();
                      const anyLock = hardLocked || lockoutActive;

                      if (!anyLock) {
                        return (
                          <div className={styles.disabledHint}>
                            현재 자동 잠금이 적용되어 있지 않습니다.
                          </div>
                        );
                      }
                      const stageLabel = hardLocked
                        ? "2차 잠금 (비밀번호 재설정 전까지)"
                        : `1차 잠금 (잔여 약 ${Math.max(
                            1,
                            Math.ceil(
                              ((lockoutUntilMs as number) - Date.now()) / 60000,
                            ),
                          )}분)`;
                      const chipClass = hardLocked
                        ? styles.lockoutChipHard
                        : styles.lockoutChipActive;
                      return (
                        <>
                          <div className={styles.actionRow}>
                            <span className={chipClass}>{stageLabel}</span>
                          </div>
                          <div className={styles.actionRow}>
                            <button
                              type="button"
                              className={styles.unblockButton}
                              onClick={handleClearLoginLockout}
                              disabled={actionPending}
                            >
                              로그인 잠금 해제
                            </button>
                          </div>
                        </>
                      );
                    }

                    if (detail.user_anomaly_throttled_at) {
                      return (
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
                      );
                    }
                    return (
                      <div className={styles.disabledHint}>
                        현재 자동 제한이 적용되어 있지 않습니다.
                      </div>
                    );
                  })()}
                </div>

                <div className={styles.actionGroup}>
                  <div className={styles.actionTitle}>차단 조치</div>
                  {(() => {
                    const blockedNow =
                      detail.user_subscription_status === "blocked";
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
