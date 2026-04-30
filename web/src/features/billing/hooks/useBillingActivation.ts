"use client";

/**
 * useBillingActivation — 빌링키 발급 → Pro 활성화 시퀀스.
 * authKey/customerKey(토스 successUrl 파라미터)를 받아:
 *   1. POST /billing/billing-key (빌링키 발급)
 *   2. POST /billing/subscriptions (최초 결제 + Pro 활성화)
 *   3. session store subscription_status 갱신
 */

import { useState } from "react";

import { useSessionStore } from "@/stores/session-store";
import { issueBillingKey, startSubscription } from "../api";

export type ActivationStatus = "idle" | "processing" | "done" | "error";

export interface UseBillingActivationResult {
  status: ActivationStatus;
  errorMessage: string | null;
  activate: (authKey: string, customerKey: string) => Promise<void>;
}

export function useBillingActivation(): UseBillingActivationResult {
  const [status, setStatus] = useState<ActivationStatus>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const currentUser = useSessionStore((s) => s.user);
  const setUser = useSessionStore((s) => s.setUser);

  async function activate(authKey: string, customerKey: string): Promise<void> {
    setStatus("processing");
    setErrorMessage(null);

    try {
      await issueBillingKey(authKey, customerKey);
      await startSubscription();

      // session store 갱신 — Pro 상태 즉시 반영
      if (currentUser) {
        setUser({ ...currentUser, subscription_status: "pro" });
      }

      setStatus("done");
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "결제 처리 중 오류가 발생했습니다.";
      setErrorMessage(message);
      setStatus("error");
    }
  }

  return { status, errorMessage, activate };
}
