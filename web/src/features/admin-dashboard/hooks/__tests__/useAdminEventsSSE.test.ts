import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook } from "@testing-library/react";
import { useAdminEventsSSE } from "../useAdminEventsSSE";
import { useAdminEventsStore } from "@/stores/admin-events-store";

// EventSource 목 구현
class MockEventSource {
  static instances: MockEventSource[] = [];
  url: string;
  withCredentials: boolean;
  listeners: Record<string, ((e: MessageEvent) => void)[]> = {};
  onerror: (() => void) | null = null;
  closed = false;

  constructor(url: string, opts?: { withCredentials?: boolean }) {
    this.url = url;
    this.withCredentials = opts?.withCredentials ?? false;
    MockEventSource.instances.push(this);
  }

  addEventListener(type: string, handler: (e: MessageEvent) => void) {
    if (!this.listeners[type]) this.listeners[type] = [];
    this.listeners[type].push(handler);
  }

  dispatchEvent(type: string, data: string) {
    const event = { data } as MessageEvent;
    this.listeners[type]?.forEach((fn) => fn(event));
  }

  close() {
    this.closed = true;
  }
}

beforeEach(() => {
  MockEventSource.instances = [];
  vi.stubGlobal("EventSource", MockEventSource);
  useAdminEventsStore.setState({
    rebuildProgress: null,
    budgetWarning: null,
    killswitchStatus: null,
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useAdminEventsSSE", () => {
  it("마운트 시 EventSource가 /api/v1/admin/events withCredentials:true로 생성된다", () => {
    renderHook(() => useAdminEventsSSE());
    expect(MockEventSource.instances).toHaveLength(1);
    expect(MockEventSource.instances[0].url).toBe("/api/v1/admin/events");
    expect(MockEventSource.instances[0].withCredentials).toBe(true);
  });

  it("언마운트 시 EventSource가 close()된다", () => {
    const { unmount } = renderHook(() => useAdminEventsSSE());
    unmount();
    expect(MockEventSource.instances[0].closed).toBe(true);
  });

  it("rag_rebuild_progress 이벤트 수신 시 스토어가 업데이트된다", () => {
    renderHook(() => useAdminEventsSSE());
    const es = MockEventSource.instances[0];
    es.dispatchEvent("rag_rebuild_progress", JSON.stringify({ percent: 30, phase: "indexing" }));
    expect(useAdminEventsStore.getState().rebuildProgress).toEqual({
      percent: 30,
      phase: "indexing",
    });
  });

  it("budget_warning 이벤트 수신 시 스토어가 업데이트된다", () => {
    renderHook(() => useAdminEventsSSE());
    const es = MockEventSource.instances[0];
    es.dispatchEvent(
      "budget_warning",
      JSON.stringify({ threshold: 95, spent_usd: 9.5, percent: 95 })
    );
    expect(useAdminEventsStore.getState().budgetWarning?.threshold).toBe(95);
  });

  it("killswitch_status 이벤트 수신 시 스토어가 업데이트된다", () => {
    renderHook(() => useAdminEventsSSE());
    const es = MockEventSource.instances[0];
    es.dispatchEvent(
      "killswitch_status",
      JSON.stringify({ mode: "auto", active: false })
    );
    expect(useAdminEventsStore.getState().killswitchStatus).toEqual({
      mode: "auto",
      active: false,
    });
  });
});
