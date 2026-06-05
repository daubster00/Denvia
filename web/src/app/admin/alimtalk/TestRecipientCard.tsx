"use client";

/**
 * Story 4.6 — 테스트 수신 번호 카드.
 *
 * 상단 카드 1곳에서 등록·변경·해제. 모든 테스트 발송 버튼은 이 한 곳의 번호만 본다.
 * sub_operator 는 입력·저장·해제 모두 disabled (조회만 허용).
 */

import { useState } from "react";
import {
  AdminAlimtalkApiError,
  clearTestRecipient,
  setTestRecipient,
  type TestRecipient,
} from "@/features/admin-alimtalk/api";
import styles from "./page.module.css";

interface Props {
  recipient: TestRecipient | null;
  canEdit: boolean;
  onChange: (next: TestRecipient) => void;
  onToast: (tone: "success" | "error" | "warn", msg: string) => void;
}

function _formatPhoneInput(raw: string): string {
  const digits = raw.replace(/\D/g, "").slice(0, 11);
  if (digits.length <= 3) return digits;
  if (digits.length <= 7) return `${digits.slice(0, 3)}-${digits.slice(3)}`;
  return `${digits.slice(0, 3)}-${digits.slice(3, 7)}-${digits.slice(7)}`;
}

export function TestRecipientCard({ recipient, canEdit, onChange, onToast }: Props) {
  const [draft, setDraft] = useState<string>("");
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState(false);

  const isSet = recipient?.is_set ?? false;
  const masked = recipient?.phone_masked ?? null;

  async function handleSave() {
    const stripped = draft.replace(/\D/g, "");
    if (!stripped) {
      onToast("warn", "휴대폰 번호를 입력하세요.");
      return;
    }
    setSaving(true);
    try {
      const next = await setTestRecipient(stripped);
      onChange(next);
      setDraft("");
      setEditing(false);
      onToast("success", `테스트 수신 번호 저장 완료 — ${next.phone_masked ?? ""}`);
    } catch (err) {
      const e = err as AdminAlimtalkApiError;
      onToast("error", e?.message ?? "수신 번호 저장 실패");
    } finally {
      setSaving(false);
    }
  }

  async function handleClear() {
    if (!confirm("테스트 수신 번호를 해제하시겠습니까?")) return;
    setSaving(true);
    try {
      await clearTestRecipient();
      onChange({ phone_masked: null, is_set: false });
      onToast("success", "테스트 수신 번호가 해제되었습니다.");
    } catch (err) {
      const e = err as AdminAlimtalkApiError;
      onToast("error", e?.message ?? "수신 번호 해제 실패");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className={styles.recipientCard} aria-labelledby="recipientLabel">
      <label id="recipientLabel" className={styles.recipientLabel}>
        테스트 발송 수신 휴대폰 번호
      </label>

      <div className={styles.recipientRow}>
        {isSet && !editing ? (
          <>
            <span className={styles.recipientMaskedDisplay}>{masked}</span>
            {canEdit && (
              <>
                <button
                  type="button"
                  className={`${styles.btn} ${styles.btnSecondary}`}
                  onClick={() => {
                    setEditing(true);
                    setDraft("");
                  }}
                  disabled={saving}
                >
                  변경
                </button>
                <button
                  type="button"
                  className={`${styles.btn} ${styles.btnDanger}`}
                  onClick={handleClear}
                  disabled={saving}
                >
                  해제
                </button>
              </>
            )}
          </>
        ) : (
          <>
            <input
              type="tel"
              inputMode="numeric"
              placeholder="010-0000-0000"
              className={styles.recipientInput}
              value={draft}
              onChange={(e) => setDraft(_formatPhoneInput(e.target.value))}
              disabled={!canEdit || saving}
              aria-label="테스트 수신 번호 입력"
            />
            <button
              type="button"
              className={`${styles.btn} ${styles.btnPrimary}`}
              onClick={handleSave}
              disabled={!canEdit || saving || draft.replace(/\D/g, "").length !== 11}
            >
              저장
            </button>
            {editing && (
              <button
                type="button"
                className={`${styles.btn} ${styles.btnSecondary}`}
                onClick={() => {
                  setEditing(false);
                  setDraft("");
                }}
                disabled={saving}
              >
                취소
              </button>
            )}
          </>
        )}
      </div>

      <p className={styles.recipientHint}>
        이 페이지의 모든 &lsquo;테스트 발송&rsquo; 버튼이 이 번호로 발송됩니다.{" "}
        <span className={styles.recipientHintEmphasis}>
          실제 알리고 한도가 차감됩니다.
        </span>
        {!canEdit && " (현재 등급에서는 조회만 가능합니다.)"}
      </p>
    </section>
  );
}
