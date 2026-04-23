import { Suspense } from "react";
import { PhoneVerifyClient } from "./PhoneVerifyClient";

export const metadata = {
  title: "소셜 가입 휴대폰 인증 — Denvia",
};

/**
 * /signup/phone-verify — Story 1.6 AC-5 / AC-12.
 * useSearchParams를 쓰는 Client Component는 Suspense 경계 내에 둔다.
 */
export default function PhoneVerifyPage() {
  return (
    <Suspense fallback={null}>
      <PhoneVerifyClient />
    </Suspense>
  );
}
