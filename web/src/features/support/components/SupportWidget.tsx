"use client";

/** SupportWidget — 우측 하단 고객 지원 위젯 (F-504). Story 4.5.
 *
 * 로그인: 1버튼(문의 작성). 비로그인: 미렌더.
 * /admin/* 라우트에서는 미렌더 (관리자는 별도 운영 채널 사용).
 *
 * 카카오톡 채널 상담 버튼은 일시적으로 숨김 처리 (사용자 요청, 추후 재도입 여지).
 * 이메일 아이콘·mailto: 절대 금지(memory project_email_zero_policy).
 */

import { usePathname } from "next/navigation";
import { useState } from "react";

import { useSessionStore } from "@/stores/session-store";

import { InquirySubmitDialog } from "./InquirySubmitDialog";
import styles from "./SupportWidget.module.css";

export function SupportWidget() {
  const pathname = usePathname();
  const user = useSessionStore((s) => s.user);
  const [dialogOpen, setDialogOpen] = useState(false);

  // /admin/* 영역에서는 미렌더 (관리자 운영 화면 분리)
  if (pathname?.startsWith("/admin")) {
    return null;
  }

  // 비로그인 사용자에게는 표시할 버튼이 없음 (카카오 버튼 숨김 상태)
  if (user === null) {
    return null;
  }

  return (
    <>
      <div role="group" aria-label="고객 지원" className={styles.widget}>
        <button
          type="button"
          onClick={() => setDialogOpen(true)}
          className={styles.inquiryBtn}
        >
          문의 작성
        </button>
      </div>
      {dialogOpen && (
        <InquirySubmitDialog onClose={() => setDialogOpen(false)} />
      )}
    </>
  );
}
