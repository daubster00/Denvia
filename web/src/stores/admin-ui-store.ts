"use client";

import { create } from "zustand";

interface AdminUiState {
  /** 모바일(<768px) 사이드바 드로어 열림 여부. 탑네비 햄버거 버튼과 사이드바가 공유. */
  mobileNavOpen: boolean;
  openMobileNav: () => void;
  closeMobileNav: () => void;
  toggleMobileNav: () => void;
}

/**
 * 관리자 셸 UI 상태 — 탑네비와 사이드바가 서로 다른 컴포넌트라
 * 모바일 드로어 열림 상태를 공유하기 위한 최소 스토어.
 * #123 — 부관리자 모바일 접근 지원.
 */
export const useAdminUiStore = create<AdminUiState>((set) => ({
  mobileNavOpen: false,
  openMobileNav: () => set({ mobileNavOpen: true }),
  closeMobileNav: () => set({ mobileNavOpen: false }),
  toggleMobileNav: () => set((s) => ({ mobileNavOpen: !s.mobileNavOpen })),
}));
