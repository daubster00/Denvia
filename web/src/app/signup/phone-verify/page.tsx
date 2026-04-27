import { Suspense } from "react";
import { PhoneVerifyClient } from "./PhoneVerifyClient";
import styles from "../signup-shell.module.css";

export const metadata = {
  title: "소셜 가입 휴대폰 인증 — Denvia",
  // 토큰 쿼리를 품는 페이지 — 검색엔진 인덱싱 차단으로 토큰 노출 방지
  robots: { index: false, follow: false },
};

/**
 * /signup/phone-verify — Story 1.6 AC-5 / AC-12.
 * useSearchParams를 쓰는 Client Component는 Suspense 경계 내에 둔다.
 */
export default function PhoneVerifyPage() {
  return (
    <Suspense
      fallback={<div aria-hidden="true" className={styles.shellPlaceholder} />}
    >
      <PhoneVerifyClient />
    </Suspense>
  );
}
