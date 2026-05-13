"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  UserPermissionUpdateError,
  type Segment,
  type SubscriptionStatus,
  type UserPermissionUpdatePayload,
  type UserSearchItem,
} from "@/features/admin-users/api/users";
import { useUpdatePermission } from "@/features/admin-users/hooks/useUpdatePermission";
import {
  SEGMENT_LABELS,
  formatSubscriptionStatus,
} from "@/features/admin-users/labels";
import styles from "./UserPermissionDialog.module.css";

interface Props {
  open: boolean;
  user: UserSearchItem | undefined;
  onClose: () => void;
  onSuccess?: () => void;
}

type DurationOption = "24" | "168" | "permanent" | "custom";

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"]), input:not([disabled]), select:not([disabled]), textarea:not([disabled])';

const ERROR_MESSAGES: Record<string, string> = {
  BLOCK_ACTION_CONFLICT: "차단과 차단 해제는 동시에 수행할 수 없습니다.",
  PRO_GRANT_CONFIRMATION_REQUIRED:
    "Pro 강제 전환은 별도 확인이 필요합니다.",
  USER_ALREADY_WITHDRAWN: "탈퇴한 사용자는 수정할 수 없습니다.",
  BLOCK_ACTION_REASON_REQUIRED: "차단 시 차단 사유를 입력해야 합니다.",
  UNBLOCK_TARGET_NOT_BLOCKED: "차단 상태가 아닌 사용자는 차단 해제할 수 없습니다.",
  BLOCK_ACTION_INVALID_FOR_STATUS:
    "차단 옵션은 차단 상태에서만 지정할 수 있습니다.",
  ADMIN_USER_NOT_FOUND: "사용자를 찾을 수 없습니다.",
};

export function UserPermissionDialog({ open, user, onClose, onSuccess }: Props) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeBtnRef = useRef<HTMLButtonElement>(null);

  const initial = user;
  const [status, setStatus] = useState<SubscriptionStatus | "">("");
  const [segment, setSegment] = useState<Segment | "">("");
  const [proConfirmChecked, setProConfirmChecked] = useState(false);
  const [quotaUseDefault, setQuotaUseDefault] = useState(true);
  const [quotaValue, setQuotaValue] = useState<string>("");
  const [duration, setDuration] = useState<DurationOption>("24");
  const [customHours, setCustomHours] = useState<string>("");
  const [reason, setReason] = useState<string>("");
  const [showUnblockConfirm, setShowUnblockConfirm] = useState(false);
  const [serverError, setServerError] = useState<{
    code: string;
    message: string;
    traceId?: string;
  } | null>(null);

  const mutation = useUpdatePermission();

  // Drawer/Dialog 열릴 때 폼 초기화 + 포커스
  useEffect(() => {
    if (!open || !initial) return;
    setStatus(initial.subscription_status);
    setSegment(initial.segment ?? "");
    setProConfirmChecked(false);
    setQuotaUseDefault(initial.daily_quota_override === null);
    setQuotaValue(
      initial.daily_quota_override !== null
        ? String(initial.daily_quota_override)
        : "",
    );
    setDuration("24");
    setCustomHours("");
    setReason("");
    setServerError(null);
    setShowUnblockConfirm(false);
    closeBtnRef.current?.focus();
  }, [open, initial]);

  // ESC 닫기 + Tab focus trap
  useEffect(() => {
    if (!open) return;

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        onClose();
        return;
      }
      if (e.key === "Tab" && dialogRef.current) {
        const focusable = dialogRef.current.querySelectorAll<HTMLElement>(
          FOCUSABLE_SELECTOR,
        );
        if (focusable.length === 0) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  const reasonLength = reason.length;
  // 신규 차단: reason 필수(1~200자). 이미 blocked인 경우: 사유 입력 시에만 1~200자 검증.
  const isNewBlock = status === "blocked" && initial?.subscription_status !== "blocked";
  const isBlockRetainWithReason =
    status === "blocked" && initial?.subscription_status === "blocked" && reasonLength > 0;
  const willSendBlockAction = isNewBlock || isBlockRetainWithReason;
  const reasonInvalid =
    (isNewBlock && (reasonLength < 1 || reasonLength > 200)) ||
    (isBlockRetainWithReason && reasonLength > 200);
  const customHoursNum = Number(customHours);
  // custom hours 검증은 block_action을 실제로 보낼 때만 필요
  const customHoursInvalid =
    willSendBlockAction &&
    duration === "custom" &&
    (!Number.isFinite(customHoursNum) ||
      customHoursNum < 1 ||
      customHoursNum > 8760);
  const quotaNum = Number(quotaValue);
  const quotaInvalid =
    !quotaUseDefault &&
    (!Number.isFinite(quotaNum) || quotaNum < 1 || quotaNum > 10000);
  const proConfirmRequired =
    status === "pro" && initial?.subscription_status !== "pro";

  const saveDisabled = useMemo(() => {
    if (!initial) return true;
    if (mutation.isPending) return true;
    if (proConfirmRequired && !proConfirmChecked) return true;
    if (status === "blocked" && reasonInvalid) return true;
    if (customHoursInvalid) return true;
    if (quotaInvalid) return true;
    return false;
  }, [
    initial,
    mutation.isPending,
    proConfirmRequired,
    proConfirmChecked,
    status,
    reasonInvalid,
    customHoursInvalid,
    quotaInvalid,
  ]);

  if (!open || !initial) return null;

  function buildPayload(): UserPermissionUpdatePayload | null {
    if (!initial) return null;
    const payload: UserPermissionUpdatePayload = {};

    // status 변경
    if (status === "blocked") {
      // 신규 차단 또는 이미 blocked 상태에서 사유를 제공해 기간/사유 수정
      // willSendBlockAction: 신규 차단이거나, 기존 blocked 상태에서 reason이 입력된 경우
      if (willSendBlockAction) {
        const durationHours: number | null =
          duration === "permanent"
            ? null
            : duration === "custom"
              ? Number(customHours)
              : Number(duration);
        payload.block_action = {
          duration_hours: durationHours,
          reason,
        };
      }
      // 이미 blocked이고 reason이 없으면 block_action 미포함 → quota 변경만 적용
    } else if (status !== initial.subscription_status) {
      if (status === "pro") {
        payload.subscription_status = "pro";
        if (proConfirmRequired) {
          payload.pro_granted_by_admin = true;
        }
      } else if (status === "free") {
        payload.subscription_status = "free";
      }
    }

    // segment 변경 — 초기값과 다르고 값이 선택된 경우에만 전송
    if (segment !== "" && segment !== initial.segment) {
      payload.segment = segment;
    }

    // quota 변경
    if (quotaUseDefault) {
      if (initial.daily_quota_override !== null) {
        payload.daily_quota_override_clear = true;
      }
    } else {
      if (Number(quotaValue) !== initial.daily_quota_override) {
        payload.daily_quota_override = Number(quotaValue);
      }
    }

    // 변경 사항이 없으면 null 반환 (no-op)
    if (Object.keys(payload).length === 0) return null;
    return payload;
  }

  async function handleSave() {
    if (!initial) return;
    setServerError(null);
    const payload = buildPayload();
    if (payload === null) {
      setServerError({
        code: "NO_CHANGES",
        message: "변경된 내용이 없습니다.",
      });
      return;
    }
    try {
      await mutation.mutateAsync({ userId: initial.user_id, payload });
      onSuccess?.();
      onClose();
    } catch (err) {
      if (err instanceof UserPermissionUpdateError) {
        setServerError({
          code: err.code,
          message: ERROR_MESSAGES[err.code] ?? err.message,
          traceId: err.traceId,
        });
      } else {
        setServerError({
          code: "UNKNOWN_ERROR",
          message: "알 수 없는 오류가 발생했습니다.",
        });
      }
    }
  }

  async function handleUnblockConfirm() {
    if (!initial) return;
    setServerError(null);
    try {
      await mutation.mutateAsync({
        userId: initial.user_id,
        payload: { unblock: true },
      });
      onSuccess?.();
      setShowUnblockConfirm(false);
      onClose();
    } catch (err) {
      if (err instanceof UserPermissionUpdateError) {
        setServerError({
          code: err.code,
          message: ERROR_MESSAGES[err.code] ?? err.message,
          traceId: err.traceId,
        });
      } else {
        setServerError({
          code: "UNKNOWN_ERROR",
          message: "알 수 없는 오류가 발생했습니다.",
        });
      }
      setShowUnblockConfirm(false);
    }
  }

  return (
    <>
      <button
        type="button"
        aria-label="닫기"
        className={styles.overlay}
        onClick={onClose}
        tabIndex={-1}
      />
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="permission-dialog-title"
        className={styles.dialog}
        data-testid="user-permission-dialog"
      >
        <header className={styles.header}>
          <h2 id="permission-dialog-title" className={styles.title}>
            권한 수정
          </h2>
          <button
            ref={closeBtnRef}
            type="button"
            onClick={onClose}
            aria-label="Dialog 닫기"
            className={styles.closeButton}
          >
            ✕
          </button>
        </header>

        <section className={styles.userInfoBox}>
          <p className={styles.userEmail}>{initial.email}</p>
          <p className={styles.userMeta}>
            ID {initial.user_id} · 현재{" "}
            <span
              className={
                initial.subscription_status === "blocked"
                  ? styles.chipBlocked
                  : initial.subscription_status === "pro"
                    ? styles.chipPro
                    : styles.chipFree
              }
            >
              {formatSubscriptionStatus(initial.subscription_status)}
            </span>
          </p>
        </section>

        <fieldset className={styles.fieldset}>
          <legend className={styles.legend}>구독 상태</legend>
          <label className={styles.radioRow}>
            <input
              type="radio"
              name="status"
              checked={status === "free"}
              onChange={() => setStatus("free")}
            />
            <span>무료 (free)</span>
          </label>
          <label className={styles.radioRow}>
            <input
              type="radio"
              name="status"
              checked={status === "pro"}
              onChange={() => setStatus("pro")}
            />
            <span>Pro (pro)</span>
          </label>
          {proConfirmRequired ? (
            <div
              className={styles.warningBox}
              role="region"
              aria-label="Pro 강제 전환 경고"
            >
              <p className={styles.warningText}>
                결제 없이 Pro 권한을 부여합니다. 결제 내역은 생성되지 않습니다.
              </p>
              <label className={styles.confirmRow}>
                <input
                  type="checkbox"
                  checked={proConfirmChecked}
                  onChange={(e) => setProConfirmChecked(e.target.checked)}
                  data-testid="pro-confirm-checkbox"
                />
                <span>확인했습니다</span>
              </label>
            </div>
          ) : null}
          <label className={styles.radioRow}>
            <input
              type="radio"
              name="status"
              checked={status === "blocked"}
              onChange={() => setStatus("blocked")}
            />
            <span>차단 (blocked)</span>
          </label>
        </fieldset>

        <fieldset className={styles.fieldset}>
          <legend className={styles.legend}>가입유형</legend>
          {(Object.keys(SEGMENT_LABELS) as Segment[]).map((value) => (
            <label key={value} className={styles.radioRow}>
              <input
                type="radio"
                name="segment"
                checked={segment === value}
                onChange={() => setSegment(value)}
                data-testid={`segment-radio-${value}`}
              />
              <span>{SEGMENT_LABELS[value]}</span>
            </label>
          ))}
        </fieldset>

        <fieldset className={styles.fieldset}>
          <legend className={styles.legend}>1일 질문 한도</legend>
          <label className={styles.checkRow}>
            <input
              type="checkbox"
              checked={quotaUseDefault}
              onChange={(e) => setQuotaUseDefault(e.target.checked)}
            />
            <span>기본값 사용</span>
          </label>
          <input
            type="number"
            min={1}
            max={10000}
            value={quotaValue}
            disabled={quotaUseDefault}
            onChange={(e) => setQuotaValue(e.target.value)}
            className={styles.numberInput}
            placeholder="1 ~ 10000"
            data-testid="quota-input"
          />
          {quotaInvalid ? (
            <p className={styles.inlineError}>1 ~ 10000 사이로 입력해주세요.</p>
          ) : null}
        </fieldset>

        {status === "blocked" ? (
          <fieldset className={styles.fieldset}>
            <legend className={styles.legend}>차단 옵션</legend>
            <label className={styles.selectRow}>
              <span>차단 기간</span>
              <select
                value={duration}
                onChange={(e) => setDuration(e.target.value as DurationOption)}
                className={styles.select}
              >
                <option value="24">24시간</option>
                <option value="168">7일</option>
                <option value="permanent">영구</option>
                <option value="custom">사용자 지정</option>
              </select>
            </label>
            {duration === "custom" ? (
              <input
                type="number"
                min={1}
                max={8760}
                value={customHours}
                onChange={(e) => setCustomHours(e.target.value)}
                className={styles.numberInput}
                placeholder="1 ~ 8760 시간"
                data-testid="custom-hours-input"
              />
            ) : null}
            {customHoursInvalid ? (
              <p className={styles.inlineError}>
                1 ~ 8760 사이로 입력해주세요.
              </p>
            ) : null}
            <label className={styles.textareaRow}>
              <span>차단 사유</span>
              <textarea
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                maxLength={200}
                className={styles.textarea}
                placeholder="1 ~ 200자 (필수)"
                data-testid="reason-textarea"
              />
              <span
                className={styles.counter}
                aria-live="polite"
                data-testid="reason-counter"
              >
                {reasonLength} / 200
              </span>
            </label>
            {reasonInvalid ? (
              <p className={styles.inlineError}>
                차단 사유를 1 ~ 200자로 입력해주세요.
              </p>
            ) : null}
          </fieldset>
        ) : null}

        {initial.subscription_status === "blocked" ? (
          <div className={styles.unblockBox}>
            <button
              type="button"
              className={styles.unblockButton}
              onClick={() => setShowUnblockConfirm(true)}
              data-testid="unblock-button"
            >
              차단 해제
            </button>
          </div>
        ) : null}

        {serverError ? (
          <div className={styles.serverErrorBox} role="alert">
            <p>{serverError.message}</p>
            {serverError.traceId ? (
              <p className={styles.traceId}>
                trace: <code>{serverError.traceId}</code>
              </p>
            ) : null}
          </div>
        ) : null}

        <footer className={styles.footer}>
          <button
            type="button"
            onClick={onClose}
            className={styles.cancelButton}
          >
            취소
          </button>
          <button
            type="button"
            disabled={saveDisabled}
            onClick={handleSave}
            className={styles.saveButton}
            data-testid="save-button"
          >
            {mutation.isPending ? "저장 중..." : "저장"}
          </button>
        </footer>

        {showUnblockConfirm ? (
          <div
            role="alertdialog"
            aria-labelledby="unblock-confirm-title"
            className={styles.confirmModal}
            data-testid="unblock-confirm"
          >
            <p id="unblock-confirm-title" className={styles.confirmText}>
              차단을 해제하시겠습니까? 사용자가 즉시 다시 이용할 수 있습니다.
            </p>
            <div className={styles.confirmActions}>
              <button
                type="button"
                onClick={() => setShowUnblockConfirm(false)}
                className={styles.cancelButton}
              >
                취소
              </button>
              <button
                type="button"
                onClick={handleUnblockConfirm}
                className={styles.dangerButton}
                data-testid="unblock-confirm-ok"
              >
                해제
              </button>
            </div>
          </div>
        ) : null}
      </div>
    </>
  );
}
