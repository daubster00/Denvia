import { describe, it, expect, beforeEach } from "vitest";
import { useQuotaStore } from "../quota-store";

const LOCK_PAYLOAD = {
  reason: "QUOTA_EXCEEDED" as const,
  dailyLimit: 10,
  usedToday: 11,
  resetAt: "2026-04-28T00:00:00+09:00",
  showUpgradePrompt: true,
  showSubscribeButton: true,
};

describe("useQuotaStore", () => {
  beforeEach(() => {
    useQuotaStore.setState({ locked: false, payload: null });
  });

  it("초기 상태는 locked=false, payload=null", () => {
    const { locked, payload } = useQuotaStore.getState();
    expect(locked).toBe(false);
    expect(payload).toBeNull();
  });

  it("lock() 호출 시 locked=true + payload 저장", () => {
    useQuotaStore.getState().lock(LOCK_PAYLOAD);
    const { locked, payload } = useQuotaStore.getState();
    expect(locked).toBe(true);
    expect(payload?.dailyLimit).toBe(10);
    expect(payload?.reason).toBe("QUOTA_EXCEEDED");
  });

  it("dismiss() 호출 시 locked=false + payload=null", () => {
    useQuotaStore.getState().lock(LOCK_PAYLOAD);
    useQuotaStore.getState().dismiss();
    const { locked, payload } = useQuotaStore.getState();
    expect(locked).toBe(false);
    expect(payload).toBeNull();
  });

  it("QUOTA_EXCEEDED_INTERNAL_SAFETY_LIMIT reason도 저장", () => {
    useQuotaStore.getState().lock({
      ...LOCK_PAYLOAD,
      reason: "QUOTA_EXCEEDED_INTERNAL_SAFETY_LIMIT",
      showUpgradePrompt: false,
      showSubscribeButton: false,
    });
    expect(useQuotaStore.getState().payload?.reason).toBe("QUOTA_EXCEEDED_INTERNAL_SAFETY_LIMIT");
  });
});
