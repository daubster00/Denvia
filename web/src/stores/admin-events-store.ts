"use client";

import { create } from "zustand";

export interface RebuildProgress {
  type: string;
  job_id: number;
  progress: number;
  stage: string;
  status?: string;
  error?: string;
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
  activeJobId: number | null;
  lastCompletedJobId: number | null;
  budgetWarning: BudgetWarning | null;
  killswitchStatus: KillswitchStatus | null;
  setRebuildProgress: (v: RebuildProgress | null) => void;
  setActiveJobId: (id: number | null) => void;
  setLastCompletedJobId: (id: number | null) => void;
  setBudgetWarning: (v: BudgetWarning | null) => void;
  setKillswitchStatus: (v: KillswitchStatus | null) => void;
}

export const useAdminEventsStore = create<AdminEventsState>((set) => ({
  rebuildProgress: null,
  activeJobId: null,
  lastCompletedJobId: null,
  budgetWarning: null,
  killswitchStatus: null,
  setRebuildProgress: (v) => set({ rebuildProgress: v }),
  setActiveJobId: (id) => set({ activeJobId: id }),
  setLastCompletedJobId: (id) => set({ lastCompletedJobId: id }),
  setBudgetWarning: (v) => set({ budgetWarning: v }),
  setKillswitchStatus: (v) => set({ killswitchStatus: v }),
}));
