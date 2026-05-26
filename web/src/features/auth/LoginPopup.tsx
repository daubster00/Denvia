"use client";

import { useEffect, useRef, useState } from "react";
import { useSessionStore } from "@/stores/session-store";
import { EmailLoginTab } from "./EmailLoginTab";
import { FindPasswordPopup } from "./FindPasswordPopup";
import { FindIdPopup } from "./FindIdPopup";
import { SignupForm } from "./SignupForm";
import styles from "@/styles/login-popup.module.css";
import { KakaoIcon, NaverIcon, GoogleIcon, EmailIcon } from "./icons";

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
  const forcePasswordReset = useSessionStore((s) => s.forcePasswordReset);
  // 비번찾기 강제 모드면 팝업을 곧장 find-password 뷰로 시작 (안내 모달 확인 후 모든
  // 후속 트리거가 비번찾기로 들어와야 한다는 요구사항).
  const [view, setView] = useState<View>(
    forcePasswordReset ? "find-password" : "buttons"
  );
  const [mode, setMode] = useState<Mode>("login");
  // find-id/find-password 뷰로 진입한 출발지. 헤더 ←와 결과 화면의 "돌아가기" 가
  // 모두 사용자가 누른 진입점으로 정확히 복귀하도록 추적한다.
  // (이메일 탭에서 진입 → "email", 첫 모듈 아래 링크에서 진입 → "buttons")
  const [findOrigin, setFindOrigin] = useState<"buttons" | "email">("email");
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
        {/* 헤더 — 뒤로 버튼(email/find-password/find-id 뷰) + 제목 + 닫기.
            forcePasswordReset 모드(2차 escalation 후)에서는 find-password 뷰의 뒤로가기를
            숨긴다 — 뒤로 가도 로그인이 즉시 다시 막혀 알림이 반복되기 때문. */}
        <div className={styles.header}>
          {((view === "email" || view === "find-id") ||
            (view === "find-password" && !forcePasswordReset)) && (
            <button
              type="button"
              onClick={() =>
                setView(
                  view === "email"
                    ? "buttons"
                    : findOrigin /* find-id / find-password */
                )
              }
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

        {/* 컨텐츠 — 모달이 화면 높이를 초과하면 내부에서 스크롤. */}
        <div className={styles.scrollBody}>
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

            {/* 로그인 모드 한정 — 첫 모듈 아래 아이디/비번 찾기 링크. 색상/문구는
                EmailLoginTab 의 동일 링크와 일치(라이트 그레이 · 13px · underline). */}
            {mode === "login" && (
              <>
                <div className={styles.findLinkRow}>
                  <button
                    type="button"
                    onClick={() => {
                      setFindOrigin("buttons");
                      setView("find-id");
                    }}
                    className={styles.findLinkBtn}
                  >
                    아이디 찾기
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setFindOrigin("buttons");
                      setView("find-password");
                    }}
                    className={styles.findLinkBtn}
                  >
                    비밀번호 찾기
                  </button>
                </div>
                <div className={styles.findLinkDivider} aria-hidden="true" />
              </>
            )}

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
          <FindPasswordPopup onBack={() => setView(findOrigin)} />
        ) : view === "find-id" ? (
          <FindIdPopup onBack={() => setView(findOrigin)} />
        ) : (
          <EmailLoginTab
            onSignup={() => setView("signup")}
            onFindPassword={() => {
              setFindOrigin("email");
              setView("find-password");
            }}
            onFindId={() => {
              setFindOrigin("email");
              setView("find-id");
            }}
          />
        )}
        </div>
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

/* ── 아이콘은 ./icons.tsx에서 import ── */
