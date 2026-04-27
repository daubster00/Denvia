"use client";

import { create } from "zustand";

interface QuotaLockPayload {
  reason: "QUOTA_EXCEEDED" | "QUOTA_EXCEEDED_INTERNAL_SAFETY_LIMIT";
  dailyLimit: number;
  usedToday: number;
  resetAt: string | null;
  showUpgradePrompt: boolean;
  showSubscribeButton: boolean;
}

interface QuotaStore {
  locked: boolean;
  payload: QuotaLockPayload | null;
  lock: (p: QuotaLockPayload) => void;
  dismiss: () => void;
}

export const useQuotaStore = create<QuotaStore>((set) => ({
  locked: false,
  payload: null,
  lock: (p) => set({ locked: true, payload: p }),
  dismiss: () => set({ locked: false, payload: null }),
}));
