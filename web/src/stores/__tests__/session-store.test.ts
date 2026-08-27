import { describe, it, expect, beforeEach } from "vitest";
import { useSessionStore } from "../session-store";

// jsdom에서 sessionStorage 모킹
const mockStorage: Record<string, string> = {};
Object.defineProperty(window, "sessionStorage", {
  value: {
    getItem: (k: string) => mockStorage[k] ?? null,
    setItem: (k: string, v: string) => { mockStorage[k] = v; },
    removeItem: (k: string) => { delete mockStorage[k]; },
    clear: () => { Object.keys(mockStorage).forEach(k => delete mockStorage[k]); },
  },
  writable: true,
});

beforeEach(() => {
  // 스토어 리셋
  useSessionStore.setState({
    user: null,
    isPopupOpen: false,
    popupInitialTab: "email",
  });
  Object.keys(mockStorage).forEach(k => delete mockStorage[k]);
});

describe("useSessionStore — clearSession", () => {
  it("clearSession이 user를 null로 처리한다", () => {
    useSessionStore.getState().setUser({
      user_id: 1,
      email: "test@example.com",
      role: "user",
      subscription_status: "free",
      segment: null,
      years_of_experience: null,
      must_reset_password: false,
      is_social: false,
    });
    expect(useSessionStore.getState().user).not.toBeNull();
    useSessionStore.getState().clearSession();
    expect(useSessionStore.getState().user).toBeNull();
  });
});

describe("useSessionStore — openPopup", () => {
  it("openPopup('social')이 초기 탭을 social로 설정한다", () => {
    useSessionStore.getState().openPopup("social");
    expect(useSessionStore.getState().isPopupOpen).toBe(true);
    expect(useSessionStore.getState().popupInitialTab).toBe("social");
  });

  it("openPopup() 기본값은 email 탭이다", () => {
    useSessionStore.getState().openPopup();
    expect(useSessionStore.getState().popupInitialTab).toBe("email");
  });

  it("closePopup이 팝업을 닫는다", () => {
    useSessionStore.getState().openPopup();
    useSessionStore.getState().closePopup();
    expect(useSessionStore.getState().isPopupOpen).toBe(false);
  });
});
