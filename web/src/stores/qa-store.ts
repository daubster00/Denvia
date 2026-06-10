"use client";

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

export interface QAMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  qaLogId?: number;
  status: "pending" | "complete" | "error";
  ruleMatched?: boolean;
  procedureCount?: number;
  timestamp: string;
}

interface QAStore {
  messages: QAMessage[];
  // 홈(/)에서 보낸 질문을 /chat 으로 라우팅이 끝난 다음 stream 으로 흘려보내기 위한 대기 슬롯.
  // 컴포넌트 useRef 는 페이지 라우팅(/ → /chat) 시 unmount 로 소실되므로 store 에 보관한다.
  pendingHomeQuestion: string | null;
  setPendingHomeQuestion: (q: string | null) => void;
  addMessage: (msg: QAMessage) => void;
  updateMessage: (id: string, patch: Partial<QAMessage>) => void;
  clearMessages: () => void;
  // 클라이언트 기획서 §3: 새 질문 시 이전 대화는 사라지고 신규 1질의응답만 표시 (atomic 교체로 hero variant 깜빡임 방지)
  replaceMessages: (msgs: QAMessage[]) => void;
  addToken: (id: string, delta: string) => void;
  markRuleMatched: (id: string, procedureCount: number) => void;
  finalize: (id: string, qaLogId: number) => void;
  setError: (id: string, message: string) => void;
}

export const useQAStore = create<QAStore>()(
  persist(
    (set) => ({
      messages: [],
      pendingHomeQuestion: null,
      setPendingHomeQuestion: (q) => set({ pendingHomeQuestion: q }),
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
    }),
    {
      name: "denvia-qa-store",
      storage: createJSONStorage(() => sessionStorage),
    }
  )
);
