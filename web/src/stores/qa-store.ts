"use client";

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

// Story 2.6: 역질문 응답 구조
export interface ReframePayload {
  followUpQuestion: string;
  options: string[];
}

export interface QAMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  qaLogId?: number;
  status: "pending" | "complete" | "error";
  ruleMatched?: boolean;
  procedureCount?: number;
  reframe?: ReframePayload;
  timestamp: string;
}

interface QAStore {
  messages: QAMessage[];
  addMessage: (msg: QAMessage) => void;
  updateMessage: (id: string, patch: Partial<QAMessage>) => void;
  clearMessages: () => void;
  // 클라이언트 기획서 §3: 새 질문 시 이전 대화는 사라지고 신규 1질의응답만 표시 (atomic 교체로 hero variant 깜빡임 방지)
  replaceMessages: (msgs: QAMessage[]) => void;
  addToken: (id: string, delta: string) => void;
  markRuleMatched: (id: string, procedureCount: number) => void;
  finalize: (id: string, qaLogId: number) => void;
  setError: (id: string, message: string) => void;
  markReframe: (id: string, payload: ReframePayload) => void;
}

export const useQAStore = create<QAStore>()(
  persist(
    (set) => ({
      messages: [],
      addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
      updateMessage: (id, patch) =>
        set((s) => ({
          messages: s.messages.map((m) => (m.id === id ? { ...m, ...patch } : m)),
        })),
      clearMessages: () => set({ messages: [] }),
      replaceMessages: (msgs) => set({ messages: msgs }),
      addToken: (id, delta) =>
        set((s) => ({
          messages: s.messages.map((m) =>
            m.id === id ? { ...m, content: m.content + delta } : m
          ),
        })),
      markRuleMatched: (id, procedureCount) =>
        set((s) => ({
          messages: s.messages.map((m) =>
            m.id === id ? { ...m, ruleMatched: true, procedureCount } : m
          ),
        })),
      finalize: (id, qaLogId) =>
        set((s) => ({
          messages: s.messages.map((m) =>
            m.id === id ? { ...m, qaLogId, status: "complete" } : m
          ),
        })),
      setError: (id, message) =>
        set((s) => ({
          messages: s.messages.map((m) =>
            m.id === id ? { ...m, content: message, status: "error" } : m
          ),
        })),
      markReframe: (id, payload) =>
        set((s) => ({
          messages: s.messages.map((m) =>
            m.id === id
              ? {
                  ...m,
                  reframe: payload,
                  // token 단계에서 누적된 자유 텍스트를 followUpQuestion으로 교체
                  // → DB answer_text 첫 줄과 화면 본문이 같은 SoT 공유 (AC-5/AC-6)
                  content: payload.followUpQuestion,
                }
              : m
          ),
        })),
    }),
    {
      name: "denvia-qa-store",
      storage: createJSONStorage(() => sessionStorage),
    }
  )
);
