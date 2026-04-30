"use client";

import { create } from "zustand";
import type { AdminSessionUser } from "@/features/admin-auth/api";

interface AdminSessionState {
  admin: AdminSessionUser | null;
  setAdmin: (a: AdminSessionUser | null) => void;
  clearAdmin: () => void;
}

/**
 * 관리자 세션 상태 — 일반 session-store와 완전히 분리.
 * persist 하지 않음 (관리자 세션 1시간 정책 — 매번 fetch로 검증).
 */
export const useAdminSessionStore = create<AdminSessionState>()((set) => ({
  admin: null,
  setAdmin: (a) => set({ admin: a }),
  clearAdmin: () => set({ admin: null }),
}));
