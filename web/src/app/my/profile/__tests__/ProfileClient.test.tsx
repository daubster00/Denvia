/** /my/profile 메인 클라이언트 — 섹션 렌더링 + 소셜/이메일 분기 + 기본정보 저장 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { ProfileClient } from "../ProfileClient";
import { useSessionStore } from "@/stores/session-store";
import { useToastStore } from "@/stores/toast-store";
import * as profileApi from "@/features/profile/api";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  usePathname: () => "/my/profile",
}));

// react-daum-postcode는 외부 DOM 스크립트를 lazy-load하므로 테스트에서 stub.
vi.mock("react-daum-postcode", () => ({
  default: () => null,
}));

// TopNav가 호출하는 InboxPreviewDropdown/unread count 의존성 회피
vi.mock("@/components/layout/TopNav", () => ({
  TopNav: () => null,
}));
vi.mock("@/components/layout/Footer", () => ({
  Footer: () => null,
}));

const mockProfile: profileApi.ProfileResponse = {
  email: "doc@denvia.com",
  name: "홍길동",
  phone: "01012345678",
  phone_verified: true,
  is_social: false,
  postcode: "12345",
  address_road: "서울시 강남구 테헤란로 1",
  address_detail: "501호",
  gender: null,
  birthdate: null,
  marketing_consent: false,
  marketing_consent_at: null,
  segment: null,
  years_of_experience: null,
};

function renderClient() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ProfileClient />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  useSessionStore.setState({
    user: {
      user_id: 1,
      email: "doc@denvia.com",
      role: "user",
      subscription_status: "free",
      segment: null,
      years_of_experience: null,
      must_reset_password: false,
      is_social: false,
    },
  });
  useToastStore.setState({ current: null });
  vi.restoreAllMocks();
});

describe("ProfileClient — 이메일 가입자", () => {
  it("3개 카드(계정정보/연락처/기본정보) 렌더링 + 이메일·이름 표시", async () => {
    vi.spyOn(profileApi, "fetchProfile").mockResolvedValue(mockProfile);
    renderClient();
    await waitFor(() => {
      expect(screen.getByText("doc@denvia.com")).toBeDefined();
    });
    expect(screen.getByRole("heading", { name: /계정정보/ })).toBeDefined();
    expect(screen.getByRole("heading", { name: /연락처/ })).toBeDefined();
    expect(screen.getByRole("heading", { name: /기본정보/ })).toBeDefined();
    // 이메일은 readonly 표시(input 아님)
    expect(screen.queryByRole("textbox", { name: /이메일/ })).toBeNull();
  });

  it("이메일 회원은 '비밀번호 변경' 버튼 노출", async () => {
    vi.spyOn(profileApi, "fetchProfile").mockResolvedValue(mockProfile);
    renderClient();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /비밀번호 변경/ })).toBeDefined();
    });
    expect(screen.queryByRole("button", { name: /비밀번호 등록/ })).toBeNull();
  });

  it("이름 변경 → 저장 시 PATCH 호출 (변경된 필드만)", async () => {
    const user = userEvent.setup();
    vi.spyOn(profileApi, "fetchProfile").mockResolvedValue(mockProfile);
    const updateSpy = vi.spyOn(profileApi, "updateProfile").mockResolvedValue();

    renderClient();
    const nameInput = (await screen.findByLabelText(/^이름$/)) as HTMLInputElement;
    await user.clear(nameInput);
    await user.type(nameInput, "김신규");
    await user.click(screen.getByRole("button", { name: /기본정보 저장/ }));

    await waitFor(() => {
      expect(updateSpy).toHaveBeenCalledWith({ name: "김신규" });
    });
  });

  it("아무것도 안 바꾸면 저장 버튼 disabled", async () => {
    vi.spyOn(profileApi, "fetchProfile").mockResolvedValue(mockProfile);
    renderClient();
    const btn = (await screen.findByRole("button", {
      name: /기본정보 저장/,
    })) as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });
});

describe("ProfileClient — 성별·생년월일·마케팅·가입유형", () => {
  it("성별 라디오 변경 → 저장 시 gender만 PATCH", async () => {
    const user = userEvent.setup();
    vi.spyOn(profileApi, "fetchProfile").mockResolvedValue(mockProfile);
    const updateSpy = vi.spyOn(profileApi, "updateProfile").mockResolvedValue();

    renderClient();
    await screen.findByRole("radiogroup", { name: /성별/ });
    await user.click(screen.getByLabelText(/^남$/));
    await user.click(screen.getByRole("button", { name: /기본정보 저장/ }));

    await waitFor(() => {
      expect(updateSpy).toHaveBeenCalledWith({ gender: "male" });
    });
  });

  it("생년월일 입력 → 저장 시 birthdate만 PATCH", async () => {
    const user = userEvent.setup();
    vi.spyOn(profileApi, "fetchProfile").mockResolvedValue(mockProfile);
    const updateSpy = vi.spyOn(profileApi, "updateProfile").mockResolvedValue();

    renderClient();
    const dateInput = (await screen.findByLabelText(
      /생년월일/,
    )) as HTMLInputElement;
    await user.type(dateInput, "1990-05-15");
    await user.click(screen.getByRole("button", { name: /기본정보 저장/ }));

    await waitFor(() => {
      expect(updateSpy).toHaveBeenCalledWith({ birthdate: "1990-05-15" });
    });
  });

  it("마케팅 '동의함' 라디오 선택 → 즉시 PATCH(marketing_consent=true)", async () => {
    const user = userEvent.setup();
    vi.spyOn(profileApi, "fetchProfile").mockResolvedValue(mockProfile);
    const updateSpy = vi.spyOn(profileApi, "updateProfile").mockResolvedValue();

    renderClient();
    const agree = (await screen.findByRole("radio", {
      name: /동의함/,
    })) as HTMLInputElement;
    const disagree = screen.getByRole("radio", {
      name: /동의하지 않음/,
    }) as HTMLInputElement;
    expect(agree.checked).toBe(false);
    expect(disagree.checked).toBe(true);
    await user.click(agree);

    await waitFor(() => {
      expect(updateSpy).toHaveBeenCalledWith({ marketing_consent: true });
    });
  });

  it("마케팅 '동의하지 않음' 라디오 선택 → 즉시 PATCH(marketing_consent=false)", async () => {
    const user = userEvent.setup();
    vi.spyOn(profileApi, "fetchProfile").mockResolvedValue({
      ...mockProfile,
      marketing_consent: true,
      marketing_consent_at: "2026-05-12T00:00:00Z",
    });
    const updateSpy = vi.spyOn(profileApi, "updateProfile").mockResolvedValue();

    renderClient();
    const disagree = (await screen.findByRole("radio", {
      name: /동의하지 않음/,
    })) as HTMLInputElement;
    expect(disagree.checked).toBe(false);
    await user.click(disagree);

    await waitFor(() => {
      expect(updateSpy).toHaveBeenCalledWith({ marketing_consent: false });
    });
  });

  it("segment=null이면 가입유형 카드는 렌더링되지 않음", async () => {
    vi.spyOn(profileApi, "fetchProfile").mockResolvedValue(mockProfile);
    renderClient();
    await screen.findByRole("heading", { name: /기본정보/ });
    expect(screen.queryByRole("heading", { name: /가입유형/ })).toBeNull();
  });

  it("segment=doctor + 연차=5면 가입유형/연차 행이 별도로 표시 (수정 불가)", async () => {
    vi.spyOn(profileApi, "fetchProfile").mockResolvedValue({
      ...mockProfile,
      segment: "doctor",
      years_of_experience: 5,
    });
    renderClient();
    await screen.findByRole("heading", { name: /가입유형/ });
    expect(screen.getByText(/치과의사/)).toBeDefined();
    expect(screen.getByText(/5년차/)).toBeDefined();
    // 가입유형 카드 안에는 폼 컨트롤이 없어야 한다(읽기 전용).
    const segmentCard = screen
      .getByRole("heading", { name: /가입유형/ })
      .closest("section");
    expect(segmentCard).not.toBeNull();
    expect(segmentCard!.querySelector("input,select,textarea")).toBeNull();
    // 가입유형/연차 라벨이 같은 카드 안에 분리된 행으로 노출되어야 함
    expect(segmentCard!.textContent).toMatch(/구분/);
    expect(segmentCard!.textContent).toMatch(/연차/);
  });

  it("segment=student_other면 연차 표기 생략", async () => {
    vi.spyOn(profileApi, "fetchProfile").mockResolvedValue({
      ...mockProfile,
      segment: "student_other",
      years_of_experience: null,
    });
    renderClient();
    await screen.findByRole("heading", { name: /가입유형/ });
    expect(screen.getByText(/학생·기타/)).toBeDefined();
    expect(screen.queryByText(/년차/)).toBeNull();
  });
});

describe("ProfileClient — 약관 카드", () => {
  it("이용약관·개인정보 처리방침 링크가 새 창 속성으로 렌더링", async () => {
    vi.spyOn(profileApi, "fetchProfile").mockResolvedValue(mockProfile);
    renderClient();
    const terms = (await screen.findByRole("link", {
      name: /이용약관/,
    })) as HTMLAnchorElement;
    const privacy = screen.getByRole("link", {
      name: /개인정보 처리방침/,
    }) as HTMLAnchorElement;
    expect(terms.getAttribute("href")).toBe("/legal/terms");
    expect(terms.getAttribute("target")).toBe("_blank");
    expect(privacy.getAttribute("href")).toBe("/legal/privacy");
    expect(privacy.getAttribute("target")).toBe("_blank");
  });
});

describe("ProfileClient — 소셜 가입자", () => {
  it("'비밀번호 등록' 버튼 노출 + '비밀번호 변경'은 없음", async () => {
    vi.spyOn(profileApi, "fetchProfile").mockResolvedValue({
      ...mockProfile,
      is_social: true,
    });
    renderClient();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /비밀번호 등록/ })).toBeDefined();
    });
    expect(screen.queryByRole("button", { name: /비밀번호 변경/ })).toBeNull();
  });
});
