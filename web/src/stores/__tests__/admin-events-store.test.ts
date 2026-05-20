import { describe, it, expect, beforeEach } from "vitest";
import { useAdminEventsStore } from "../admin-events-store";

beforeEach(() => {
  useAdminEventsStore.setState({
    rebuildProgress: null,
    budgetWarning: null,
    killswitchStatus: null,
  });
});

describe("useAdminEventsStore", () => {
  it("초기 상태는 모두 null이다", () => {
    const state = useAdminEventsStore.getState();
    expect(state.rebuildProgress).toBeNull();
    expect(state.budgetWarning).toBeNull();
    expect(state.killswitchStatus).toBeNull();
  });

  it("setRebuildProgress가 rebuildProgress를 업데이트한다", () => {
    useAdminEventsStore.getState().setRebuildProgress({ percent: 50, phase: "embedding" });
    expect(useAdminEventsStore.getState().rebuildProgress).toEqual({
      percent: 50,
      phase: "embedding",
    });
  });

  it("setRebuildProgress(null)로 초기화할 수 있다", () => {
    useAdminEventsStore.getState().setRebuildProgress({ percent: 100 });
    useAdminEventsStore.getState().setRebuildProgress(null);
    expect(useAdminEventsStore.getState().rebuildProgress).toBeNull();
  });

  it("setBudgetWarning이 budgetWarning을 업데이트한다", () => {
    useAdminEventsStore
      .getState()
      .setBudgetWarning({ threshold: 80, spent_krw: 11_200, percent: 80 });
    const state = useAdminEventsStore.getState();
    expect(state.budgetWarning?.threshold).toBe(80);
    expect(state.budgetWarning?.percent).toBe(80);
    expect(state.budgetWarning?.spent_krw).toBe(11_200);
  });

  it("setKillswitchStatus가 killswitchStatus를 업데이트한다", () => {
    useAdminEventsStore
      .getState()
      .setKillswitchStatus({ mode: "manual", active: true });
    expect(useAdminEventsStore.getState().killswitchStatus).toEqual({
      mode: "manual",
      active: true,
    });
  });
});
