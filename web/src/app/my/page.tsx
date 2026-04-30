"use client";

/**
 * 마이페이지 — Story 4.3.
 * AccountSummary KPI 카드 + 결제 내역 placeholder section (Story 4.4 마운트 지점).
 *
 * 인증 가드: SessionBootstrap이 비동기로 store.user를 채우는 동안 store만 보면
 * 유효 세션 사용자도 직접 진입/새로고침 시 홈으로 튕기는 race가 발생한다.
 * 따라서 ["session"] TanStack Query 캐시(이미 SessionBootstrap이 prefetch)를
 * 직접 구독해서 pending 동안에는 null 렌더링, isError가 확정된 시점에만 팝업/리다이렉트.
 */

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";

import { TopNav } from "@/components/layout/TopNav";
import { AccountSummary } from "@/features/account/components/AccountSummary";
import { PaymentHistoryTable } from "@/features/billing/components/PaymentHistoryTable";
import { fetchMe } from "@/features/auth/api";
import { useSessionStore } from "@/stores/session-store";

import styles from "./page.module.css";

export default function MyPage() {
  const router = useRouter();
  const user = useSessionStore((s) => s.user);
  const openPopup = useSessionStore((s) => s.openPopup);

  const { isLoading, data, isError } = useQuery({
    queryKey: ["session"],
    queryFn: fetchMe,
    retry: 1,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });

  useEffect(() => {
    if (!isLoading && isError && user == null) {
      openPopup("email");
      router.replace("/?login=required");
    }
  }, [isLoading, isError, user, openPopup, router]);

  if ((isLoading && user == null) || (data == null && user == null)) {
    return null;
  }

  return (
    <>
      <TopNav />
      <main className={styles.container}>
        <h1 className={styles.heading}>마이페이지</h1>
        <AccountSummary />
        <section
          id="payment-history"
          className={styles.paymentHistorySection}
          aria-label="결제 내역"
        >
          <h2 className={styles.sectionHeading}>결제 내역</h2>
          <PaymentHistoryTable />
        </section>
      </main>
    </>
  );
}
