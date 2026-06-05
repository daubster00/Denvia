"use client";

/**
 * Story 4.6 — 템플릿 한 행 + 테스트 발송 + 상세보기 링크.
 *
 * 2026-06-05 갱신:
 * - "로그 보기" → "상세보기" — 모달이 아니라 `/admin/alimtalk/[code]` 페이지로 이동.
 * - "템플릿 코드" 컬럼은 알리고 등록 코드(UH_/UI_)만 노출. 미등록·SMS는 별도 표기.
 * - 채널 칩(알림톡/SMS) 추가.
 */

import Link from "next/link";
import { useState } from "react";
import {
  AdminAlimtalkApiError,
  dispatchTestSend,
  type AlimtalkTemplateStat,
} from "@/features/admin-alimtalk/api";
import { labelForCategory } from "@/features/admin-alimtalk/categoryColors";
import styles from "./page.module.css";

interface Props {
  template: AlimtalkTemplateStat;
  isRecipientSet: boolean;
  canTestSend: boolean;
  quotaReached: boolean;
  onSendComplete: () => void;
  onToast: (tone: "success" | "error" | "warn", msg: string) => void;
}

export function TemplateRow({
  template,
  isRecipientSet,
  canTestSend,
  quotaReached,
  onSendComplete,
  onToast,
}: Props) {
  const [sending, setSending] = useState(false);

  const sendDisabled = !canTestSend || !isRecipientSet || quotaReached || sending;
  const sendTooltip = !canTestSend
    ? "현재 등급에서는 테스트 발송이 불가능합니다."
    : !isRecipientSet
      ? "테스트 수신 번호를 먼저 등록해주세요."
      : quotaReached
        ? "오늘의 테스트 발송 한도(20건)를 모두 사용했습니다."
        : undefined;

  async function handleSend() {
    setSending(true);
    try {
      const result = await dispatchTestSend(template.template_code);
      if (result.success) {
        onToast("success", `발송 성공 — ${template.title} → ${result.phone_masked ?? ""}`);
      } else {
        onToast(
          "warn",
          `발송 실패 — ${result.error_message ?? "알리고 reject"} (code=${result.aligo_response_code})`,
        );
      }
      onSendComplete();
    } catch (err) {
      const e = err as AdminAlimtalkApiError;
      if (e?.code === "ALIMTALK_TEST_SEND_QUOTA_EXCEEDED") {
        onToast("error", e.message);
        onSendComplete();
      } else {
        onToast("error", e?.message ?? "테스트 발송에 실패했습니다.");
      }
    } finally {
      setSending(false);
    }
  }

  // 템플릿 코드 컬럼 표기 — 알리고 등록 코드만. SMS·미등록은 별도 라벨.
  const isSms = template.channel === "sms";
  const tplCodeDisplay = isSms
    ? "—"
    : template.aligo_tpl_code ?? "미등록";
  const tplCodeIsMissing = !isSms && !template.aligo_tpl_code;

  return (
    <tr>
      <td>
        <span className={styles.channelChip} data-channel={template.channel}>
          {isSms ? "SMS" : "알림톡"}
        </span>
      </td>
      <td>
        <span className={styles.chip} data-category={template.category}>
          {labelForCategory(template.category)}
        </span>
      </td>
      <td
        className={styles.tableTemplateCode}
        data-missing={tplCodeIsMissing ? "true" : undefined}
      >
        {tplCodeDisplay}
      </td>
      <td className={styles.tableTemplateTitle}>{template.title}</td>
      <td className={styles.tableCount}>
        {template.today_sent} /{" "}
        <span className={template.today_failed > 0 ? styles.tableCountFailed : ""}>
          {template.today_failed}
        </span>
      </td>
      <td className={styles.tableCount}>
        {template.month_sent} /{" "}
        <span className={template.month_failed > 0 ? styles.tableCountFailed : ""}>
          {template.month_failed}
        </span>
      </td>
      <td>
        <div className={styles.tableActions}>
          <button
            type="button"
            className={`${styles.btn} ${styles.btnPrimary} ${styles.btnSmall}`}
            onClick={handleSend}
            disabled={sendDisabled}
            title={sendTooltip}
          >
            {sending ? "발송 중…" : "테스트 발송"}
          </button>
          <Link
            href={`/admin/alimtalk/${encodeURIComponent(template.template_code)}`}
            className={`${styles.btn} ${styles.btnSecondary} ${styles.btnSmall}`}
          >
            상세보기
          </Link>
        </div>
      </td>
    </tr>
  );
}
