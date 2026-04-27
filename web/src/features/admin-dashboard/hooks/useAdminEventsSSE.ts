import { useEffect } from "react";
import { useAdminEventsStore } from "@/stores/admin-events-store";

export function useAdminEventsSSE() {
  const { setRebuildProgress, setBudgetWarning, setKillswitchStatus } =
    useAdminEventsStore();

  useEffect(() => {
    // GET 기반 SSE — 표준 EventSource 사용 (fetch-event-source는 POST/Q&A SSE 전용)
    const es = new EventSource("/api/v1/admin/events", { withCredentials: true });

    es.addEventListener("rag_rebuild_progress", (e: MessageEvent) => {
      setRebuildProgress(JSON.parse(e.data));
    });
    es.addEventListener("budget_warning", (e: MessageEvent) => {
      setBudgetWarning(JSON.parse(e.data));
    });
    es.addEventListener("killswitch_status", (e: MessageEvent) => {
      setKillswitchStatus(JSON.parse(e.data));
    });

    es.onerror = () => {
      // 재연결은 EventSource가 자동 처리
    };

    return () => es.close();
  }, []); // 마운트 1회만
}
