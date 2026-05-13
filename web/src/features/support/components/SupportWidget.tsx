"use client";

/** SupportWidget — 우측 하단 고객 지원 위젯 (F-504). Story 4.5 + 0030 게시판화.
 *
 * 클릭 시 즉시 작성 페이지(/my/inquiries/new)로 이동한다. 모달 형식 폐기.
 * 비로그인/관리자 화면에서는 미렌더 (기존 정책 유지).
 * 이메일 아이콘·mailto: 절대 금지(memory project_email_zero_policy).
 */

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useSessionStore } from "@/stores/session-store";

import styles from "./SupportWidget.module.css";

export function SupportWidget() {
  const pathname = usePathname();
  const user = useSessionStore((s) => s.user);

  if (pathname?.startsWith("/admin")) {
    return null;
  }

  if (user === null) {
    return null;
  }

  return (
    <div role="group" aria-label="고객 지원" className={styles.widget}>
      <Link href="/my/inquiries/new" className={styles.inquiryBtn}>
        문의 작성
      </Link>
    </div>
  );
}
