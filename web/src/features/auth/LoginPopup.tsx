"use client";

import { useEffect, useRef, useState } from "react";
import { useSessionStore } from "@/stores/session-store";
import { EmailLoginTab } from "./EmailLoginTab";
import { FindPasswordPopup } from "./FindPasswordPopup";
import { FindIdPopup } from "./FindIdPopup";
import { SignupForm } from "./SignupForm";
import styles from "@/styles/login-popup.module.css";

type View = "buttons" | "email" | "signup" | "find-password" | "find-id";
type Mode = "login" | "signup";

/**
 * 로그인 팝업.
 * - buttons 뷰: 소셜/이메일 선택
 * - email 뷰: EmailLoginTab (← 뒤로 버튼으로 복귀)
 * - mode: login/signup → 버튼 텍스트 "OOO로 로그인" / "OOO로 가입하기"
 * - Focus trap, ESC 닫힘, 배경 클릭 닫힘 없음 (UX Spec §1439)
 */
export function LoginPopup() {
  const closePopup = useSessionStore((s) => s.closePopup);
  const [view, setView] = useState<View>("buttons");
  const [mode, setMode] = useState<Mode>("login");
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeBtnRef = useRef<HTMLButtonElement>(null);
  // 소셜 버튼 더블클릭·OAuth 이동 중복 실행 가드 (페이지 내 single-shot)
  const navigatingRef = useRef(false);

  // body scroll lock은 LoginPopupMount에서 isPopupOpen 상태에 직접 연결되어 관리된다.
  // 여기서 중복 조작하면 외부 이동(window.location.href) 후 복귀 시 잔류 위험.

  // 뷰 전환 시 첫 포커스 이동
  useEffect(() => {
    if (view === "buttons") {
      const firstBtn = dialogRef.current?.querySelector<HTMLElement>(
        'button:not([aria-label="팝업 닫기"]):not([aria-label="이전 화면으로"])'
      );
      firstBtn?.focus();
    } else if (view === "email") {
      const emailInput = dialogRef.current?.querySelector<HTMLElement>('input[type="email"]');
      emailInput?.focus();
    }
  }, [view]);

  // ESC 닫힘 + focus trap
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") closePopup();
      if (e.key === "Tab") trapFocus(e);
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [closePopup]);

  function trapFocus(e: KeyboardEvent) {
    if (!dialogRef.current) return;
    const focusable = dialogRef.current.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])'
    );
    if (focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (e.shiftKey) {
      if (document.activeElement === first) { e.preventDefault(); last.focus(); }
    } else {
      if (document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  }

  const loginSuffix = mode === "login" ? "로 로그인" : "로 가입하기";

  const title =
    view === "signup"
      ? "이메일로 회원가입"
      : view === "find-password"
      ? "비밀번호 찾기"
      : view === "find-id"
      ? "아이디 찾기"
      : view === "email"
      ? mode === "login" ? "이메일로 로그인" : "이메일로 가입하기"
      : mode === "login" ? "로그인" : "회원가입";

  const handleSocial = (provider: "kakao" | "naver" | "google") => {
    if (navigatingRef.current) return;
    navigatingRef.current = true;
    // 외부 이동 전 팝업 닫기 — 뒤로가기 복귀 시 잔류 state 방지
    closePopup();
    // trailing slash 제거로 `//api/` 같은 이중 슬래시 방지
    const apiBase = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
    const params = new URLSearchParams({ mode });
    window.location.href = `${apiBase}/api/v1/auth/oauth/${provider}/authorize?${params}`;
  };

  return (
    <>
      {/* 배경 오버레이 — 클릭해도 닫히지 않음 (UX Spec §1439) */}
      <div aria-hidden="true" className={styles.overlay} />

      {/* 팝업 다이얼로그 */}
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="login-popup-title"
        className={styles.dialog}
      >
        {/* 헤더 — 뒤로 버튼(email/find-password/find-id 뷰) + 제목 + 닫기 */}
        <div className={styles.header}>
          {(view === "email" || view === "find-password" || view === "find-id") && (
            <button
              type="button"
              onClick={() => setView(view === "email" ? "buttons" : "email")}
              aria-label="이전 화면으로"
              className={styles.backBtn}
            >
              ←
            </button>
          )}
          <h2 id="login-popup-title" className={styles.title}>
            {title}
          </h2>
          <button
            ref={closeBtnRef}
            type="button"
            onClick={closePopup}
            aria-label="팝업 닫기"
            className={styles.closeBtn}
          >
            ✕
          </button>
        </div>

        {/* 컨텐츠 */}
        {view === "buttons" ? (
          <>
            <div className={styles.buttonStack}>
              {/* 네이버 */}
              <LoginButton
                label={`네이버${loginSuffix}`}
                variant="naver"
                onClick={() => handleSocial("naver")}
                icon={<NaverIcon />}
                ariaLabel={`네이버${loginSuffix}`}
              />

              {/* 카카오 */}
              <LoginButton
                label={`카카오${loginSuffix}`}
                variant="kakao"
                onClick={() => handleSocial("kakao")}
                icon={<KakaoIcon />}
                ariaLabel={`카카오${loginSuffix}`}
              />

              {/* 구글 */}
              <LoginButton
                label={`구글${loginSuffix}`}
                variant="google"
                onClick={() => handleSocial("google")}
                icon={<GoogleIcon />}
                ariaLabel={`구글${loginSuffix}`}
              />

              {/* 구분선 */}
              <div className={styles.divider}>
                <div className={styles.dividerLine} />
                <span className={styles.dividerLabel}>또는</span>
                <div className={styles.dividerLine} />
              </div>

              {/* 이메일 — 로그인 모드: 이메일 로그인 폼 / 가입 모드: 가입 폼 */}
              <LoginButton
                label={`이메일${loginSuffix}`}
                variant="email"
                onClick={() => setView(mode === "signup" ? "signup" : "email")}
                icon={<EmailIcon />}
                ariaLabel={`이메일${loginSuffix}`}
              />
            </div>

            {/* 로그인 ↔ 회원가입 전환 */}
            <p className={styles.modeSwitch}>
              {mode === "login" ? (
                <>
                  아직 회원이 아니신가요?{" "}
                  <button
                    type="button"
                    onClick={() => setMode("signup")}
                    className={styles.modeSwitchBtn}
                  >
                    회원가입
                  </button>
                </>
              ) : (
                <>
                  이미 회원이신가요?{" "}
                  <button
                    type="button"
                    onClick={() => setMode("login")}
                    className={styles.modeSwitchBtn}
                  >
                    로그인
                  </button>
                </>
              )}
            </p>
          </>
        ) : view === "signup" ? (
          <SignupForm />
        ) : view === "find-password" ? (
          <FindPasswordPopup onBack={() => setView("email")} />
        ) : view === "find-id" ? (
          <FindIdPopup onBack={() => setView("email")} />
        ) : (
          <EmailLoginTab
            onSignup={() => setView("signup")}
            onFindPassword={() => setView("find-password")}
            onFindId={() => setView("find-id")}
          />
        )}
      </div>
    </>
  );
}

/* ── 공통 버튼 ── */

type SocialVariant = "naver" | "kakao" | "google" | "email";

interface LoginButtonProps {
  label: string;
  variant: SocialVariant;
  onClick: () => void;
  icon: React.ReactNode;
  ariaLabel: string;
}

const variantClass: Record<SocialVariant, string> = {
  naver: styles.socialBtnNaver,
  kakao: styles.socialBtnKakao,
  google: styles.socialBtnGoogle,
  email: styles.socialBtnEmail,
};

function LoginButton({ label, variant, onClick, icon, ariaLabel }: LoginButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={ariaLabel}
      className={`${styles.socialBtn} ${variantClass[variant]}`}
    >
      <span className={styles.socialIcon}>{icon}</span>
      <span className={styles.socialLabel}>{label}</span>
      <span className={styles.socialSpacer} aria-hidden="true" />
    </button>
  );
}

/* ── 아이콘 ── */

function NaverIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false">
      <path d="M16.273 12.845L7.376 0H0v24h7.727V11.155L16.624 24H24V0h-7.727z" fill="white" />
    </svg>
  );
}

function KakaoIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" focusable="false">
      <path d="M12.0009 3C17.7999 3 22.501 6.66445 22.501 11.1847C22.501 15.705 17.7999 19.3694 12.0009 19.3694C11.4127 19.3694 10.8361 19.331 10.2742 19.2586L5.86611 22.1419C5.36471 22.4073 5.18769 22.3778 5.39411 21.7289L6.28571 18.0513C3.40572 16.5919 1.50098 14.0619 1.50098 11.1847C1.50098 6.66445 6.20194 3 12.0009 3ZM17.908 11.0591L19.3783 9.63617C19.5656 9.45485 19.5705 9.15617 19.3893 8.96882C19.2081 8.78172 18.9094 8.77668 18.7219 8.95788L16.7937 10.8239V9.28226C16.7937 9.02172 16.5825 8.81038 16.3218 8.81038C16.0613 8.81038 15.8499 9.02172 15.8499 9.28226V11.8393C15.8321 11.9123 15.8325 11.9879 15.8499 12.0611V13.5C15.8499 13.7606 16.0613 13.9719 16.3218 13.9719C16.5825 13.9719 16.7937 13.7606 16.7937 13.5V12.1373L17.2213 11.7236L18.6491 13.7565C18.741 13.8873 18.8873 13.9573 19.0357 13.9573C19.1295 13.9573 19.2241 13.9293 19.3066 13.8714C19.5199 13.7217 19.5713 13.4273 19.4215 13.214L17.908 11.0591ZM14.9503 12.9839H13.4904V9.29702C13.4904 9.03648 13.2791 8.82514 13.0184 8.82514C12.7579 8.82514 12.5467 9.03648 12.5467 9.29702V13.4557C12.5467 13.7164 12.7579 13.9276 13.0184 13.9276H14.9503C15.211 13.9276 15.4222 13.7164 15.4222 13.4557C15.4222 13.1952 15.211 12.9839 14.9503 12.9839ZM9.09318 11.8925L9.78919 10.1849L10.4265 11.8925H9.09318ZM11.6159 12.3802C11.6161 12.3748 11.6175 12.3699 11.6175 12.3645C11.6175 12.2405 11.5687 12.1287 11.4906 12.0445L10.4452 9.24376C10.3468 8.9639 10.1005 8.77815 9.81761 8.77028C9.53948 8.76277 9.28066 8.93672 9.16453 9.21669L7.50348 13.2924C7.40519 13.5337 7.52107 13.8092 7.76242 13.9076C8.00378 14.006 8.2792 13.89 8.37749 13.6486L8.70852 12.8364H10.7787L11.077 13.6356C11.1479 13.8254 11.3278 13.9426 11.5193 13.9425C11.5741 13.9425 11.6298 13.9329 11.6842 13.9126C11.9284 13.8216 12.0524 13.5497 11.9612 13.3054L11.6159 12.3802ZM8.29446 9.30194C8.29446 9.0414 8.08312 8.83006 7.82258 8.83006H4.57822C4.31755 8.83006 4.10622 9.0414 4.10622 9.30194C4.10622 9.56249 4.31755 9.77382 4.57822 9.77382H5.73824V13.5099C5.73824 13.7705 5.94957 13.9817 6.21012 13.9817C6.47078 13.9817 6.68212 13.7705 6.68212 13.5099V9.77382H7.82258C8.08312 9.77382 8.29446 9.56249 8.29446 9.30194Z" />
    </svg>
  );
}

function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true" focusable="false">
      <path fill="#4285F4" d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.875 2.684-6.615z" />
      <path fill="#34A853" d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18z" />
      <path fill="#FBBC05" d="M3.964 10.71A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 0 0 0 9c0 1.452.348 2.827.957 4.042l3.007-2.332z" />
      <path fill="#EA4335" d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.958L3.964 6.29C4.672 4.163 6.656 3.58 9 3.58z" />
    </svg>
  );
}

function EmailIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false">
      <rect x="2" y="4" width="20" height="16" rx="3" stroke="#5A5C63" strokeWidth="1.8" />
      <path d="M2 8l10 7 10-7" stroke="#5A5C63" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}
