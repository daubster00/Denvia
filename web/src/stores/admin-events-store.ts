"use client";

import { create } from "zustand";

interface RebuildProgress {
  percent: number;
  phase?: string;
}

interface BudgetWarning {
  threshold: 80 | 95;
  spent_usd: number;
  percent: number;
}

interface KillswitchStatus {
  mode: string;
  active: boolean;
}

interface AdminEventsState {
  rebuildProgress: RebuildProgress | null;
  budgetWarning: BudgetWarning | null;
  killswitchStatus: KillswitchStatus | null;
  setRebuildProgress: (v: RebuildProgress | null) => void;
  setBudgetWarning: (v: BudgetWarning | null) => void;
  setKillswitchStatus: (v: KillswitchStatus | null) => void;
}

export const useAdminEventsStore = create<AdminEventsState>((set) => ({
  rebuildProgress: null,
  budgetWarning: null,
  killswitchStatus: null,
  setRebuildProgress: (v) => set({ rebuildProgress: v }),
  setBudgetWarning: (v) => set({ budgetWarning: v }),
  setKillswitchStatus: (v) => set({ killswitchStatus: v }),
}));
