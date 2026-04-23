"use client";

import { create } from "zustand";

export type AlertLevel = "error" | "warning" | "info";

export interface AlertAction {
  label: string;
  /** 닫힘 + 실행. onClick 없으면 단순 닫기 버튼. */
  onClick?: () => void;
  /** assistive: 회색 · negative: 빨강 · 기본: 보라 */
  variant?: "normal" | "assistive" | "negative";
}

export interface AlertPayload {
  level: AlertLevel;
  /** 제목 — heading1 */
  title: string;
  /** 본문 설명 — body2-reading */
  description?: string;
  /** 확인·취소 등 액션 버튼 배열. 미지정 시 기본 "확인" 단일 버튼. */
  actions?: AlertAction[];
  /** 같은 코드의 알림이 연속 트리거되지 않도록 dedupe */
  dedupeKey?: string;
}

interface AlertState {
  current: AlertPayload | null;
  /** 글로벌 호출 API — 어디서든 호출 가능 */
  show: (payload: AlertPayload) => void;
  close: () => void;
}

export const useAlertStore = create<AlertState>((set, get) => ({
  current: null,
  show: (payload) => {
    const prev = get().current;
    // 같은 dedupeKey가 이미 표시 중이면 무시
    if (prev && payload.dedupeKey && prev.dedupeKey === payload.dedupeKey) {
      return;
    }
    set({ current: payload });
  },
  close: () => set({ current: null }),
}));
