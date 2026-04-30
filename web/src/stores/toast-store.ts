"use client";

/** 가벼운 토스트 store — Story 4.3.
 *
 * 자동 dismiss(기본 2초). 외부 의존성 없음(NFR-P5 번들 보호).
 * 글로벌 AppAlert가 blocking 모달이라면 본 토스트는 비-블로킹 안내용.
 */

import { create } from "zustand";

interface ToastState {
  current: { id: number; message: string } | null;
  show: (message: string, durationMs?: number) => void;
  dismiss: () => void;
}

let _seq = 0;

export const useToastStore = create<ToastState>((set, get) => ({
  current: null,
  show: (message, durationMs = 2000) => {
    _seq += 1;
    const id = _seq;
    set({ current: { id, message } });
    if (typeof window !== "undefined") {
      window.setTimeout(() => {
        if (get().current?.id === id) {
          set({ current: null });
        }
      }, durationMs);
    }
  },
  dismiss: () => set({ current: null }),
}));
