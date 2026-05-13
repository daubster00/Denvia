"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";

import { useQuery } from "@tanstack/react-query";

import { TopNav } from "@/components/layout/TopNav";
import { Footer } from "@/components/layout/Footer";
import { fetchMe } from "@/features/auth/api";
import { BillingKeyForm } from "@/features/billing/components/BillingKeyForm";
import { CancelSubscriptionFlow } from "@/features/billing/components/CancelSubscriptionFlow";
import { PricingCard } from "@/features/billing/components/PricingCard";
import { SubscriptionStatusCard } from "@/features/billing/components/SubscriptionStatusCard";
import { useBillingActivation } from "@/features/billing/hooks/useBillingActivation";
import { useBillingPlans } from "@/features/billing/hooks/useBillingPlans";
import { useCurrentSubscription } from "@/features/billing/hooks/useCurrentSubscription";
import { useResumeSubscription } from "@/features/billing/hooks/useResumeSubscription";
import { apiFetch } from "@/lib/api-client";
import { useSessionStore } from "@/stores/session-store";
import styles from "./subscribe.module.css";

/** URL 파라미터를 읽어 billing_auth_ok 처리를 트리거하는 내부 컴포넌트. */
function BillingAuthProcessor() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { activate, status, errorMessage } = useBillingActivation();

  const step = searchParams.get("step");
  const authKey = searchParams.get("authKey");
  const customerKey = searchParams.get("customerKey");

  useEffect(() => {
    if (step === "billing_auth_ok" && authKey && customerKey && status === "idle") {
      void activate(authKey, customerKey);
    }
  }, [step, authKey, customerKey, status, activate]);

  useEffect(() => {
    if (status === "done") {
      router.replace("/");
    }
  }, [status, router]);

  if (step === "billing_auth_fail") {
    return (
      <p className={styles.authError}>
        카드 등록이 취소되었습니다. 다시 시도해주세요.
      </p>
    );
  }

  if (step === "billing_auth_ok" && (status === "idle" || status === "processing")) {
    return (
      <div className={styles.loading} role="status" aria-live="polite">
        <span className={styles.loadingText}>결제 처리 중...</span>
      </div>
    );
  }

  if (status === "error") {
    return (
      <p className={styles.authError}>
        {errorMessage || "결제 처리 중 오류가 발생했습니다. 다시 시도해주세요."}
      </p>
    );
  }

  return null;
}

function SubscribeContent() {
  const openPopup = useSessionStore((s) => s.openPopup);
  const [isBillingFormOpen, setIsBillingFormOpen] = useState(false);
  const [isCancelFlowOpen, setIsCancelFlowOpen] = useState(false);

  const {
    data: sessionData,
    isLoading: sessionLoading,
    isError: sessionIsError,
  } = useQuery({
    queryKey: ["session"],
    queryFn: fetchMe,
    retry: 0,
    staleTime: 60_000,
  });

  // /api/v1/me는 api-client 401 인터셉터 제외 대상이므로 여기서 직접 감지
  useEffect(() => {
    if (!sessionLoading && sessionIsError) {
      openPopup("email");
      const url = new URL(window.location.href);
      url.searchParams.set("next", "/subscribe");
      window.history.replaceState(null, "", url.toString());
    }
  }, [sessionLoading, sessionIsError, openPopup]);

  const isAuthenticated = !sessionLoading && !!sessionData;
  const { data: plansData, isLoading: plansLoading } = useBillingPlans({
    enabled: isAuthenticated,
  });

  const { data: currentSub } = useCurrentSubscription({
    enabled: isAuthenticated,
  });
  const resumeMutation = useResumeSubscription();

  useEffect(() => {
    if (!sessionData) return;
    apiFetch<void>("/api/v1/events/client", {
      method: "POST",
      body: JSON.stringify({ event: "billing.plans.viewed" }),
    }).catch(() => undefined);
  }, [sessionData]);

  const handleProCta = useCallback(() => {
    setIsBillingFormOpen(true);
  }, []);

  const handleResumeClick = useCallback(() => {
    if (resumeMutation.isPending) return;
    resumeMutation.mutate();
  }, [resumeMutation]);

  const isLoading = sessionLoading || plansLoading;
  const showStatusCard =
    isAuthenticated &&
    currentSub &&
    (currentSub.status === "active" || currentSub.status === "cancel_pending");
  const showPricingCards =
    !isLoading && plansData && (!currentSub || currentSub.status === "none");

  return (
    <div className={styles.page}>
      <TopNav />
      <main className={styles.main}>
        <div className={styles.hero}>
          <h1 className={styles.title}>Denvia 플랜 선택</h1>
          <p className={styles.subtitle}>
            치과 보험청구·행정 Q&A를 더 스마트하게 — Pro로 무제한 이용하세요
          </p>
        </div>

        {/* 토스 successUrl/failUrl 복귀 처리 */}
        <Suspense fallback={null}>
          <BillingAuthProcessor />
        </Suspense>

        {isLoading && (
          <div className={styles.loading} role="status" aria-live="polite">
            <span className={styles.loadingText}>플랜 정보를 불러오는 중...</span>
          </div>
        )}

        {showStatusCard && currentSub.status === "active" && (
          <SubscriptionStatusCard
            variant="active"
            nextChargeAt={currentSub.next_charge_at}
            onCancelClick={() => setIsCancelFlowOpen(true)}
          />
        )}

        {showStatusCard && currentSub.status === "cancel_pending" && (
          <SubscriptionStatusCard
            variant="cancel_pending"
            effectiveAt={currentSub.current_period_end}
            onResumeClick={handleResumeClick}
            isResuming={resumeMutation.isPending}
          />
        )}

        {showPricingCards && (
          <div className={styles.cardRow}>
            {plansData.plans.map((plan) => (
              <PricingCard
                key={plan.tier}
                plan={plan}
                onCta={plan.tier === "pro" ? handleProCta : undefined}
              />
            ))}
          </div>
        )}
      </main>

      <Footer />

      <BillingKeyForm
        isOpen={isBillingFormOpen}
        onClose={() => setIsBillingFormOpen(false)}
      />

      <CancelSubscriptionFlow
        isOpen={isCancelFlowOpen}
        onClose={() => setIsCancelFlowOpen(false)}
        currentPeriodEnd={currentSub?.current_period_end ?? null}
      />
    </div>
  );
}

export default function SubscribePage() {
  return (
    <Suspense fallback={null}>
      <SubscribeContent />
    </Suspense>
  );
}
