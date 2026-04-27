"use client";

import { useSessionStore } from "@/stores/session-store";
import { LogoLink } from "@/components/brand/LogoLink";
import { useLogout } from "@/features/auth/hooks/useLogout";
import styles from "./TopNav.module.css";

interface TopNavProps {
  onResetChat?: () => void;
}

/**
 * 상단 네비게이션 바.
 * 좌측: 로고 (Story 2.5 F-306 onResetChat 트리거).
 * 우측 — 비로그인: "로그인" 버튼(T1 gradient) / 로그인 후: 이메일 + "로그아웃" 버튼 (Story 2.7 미니 메뉴).
 *
 * 풀 메뉴 4종(쪽지함·계정 드롭다운·마이·구독)은 Epic 3·4·4-5 진행 시 점진 확장 — 본 스토리 비범위.
 * components/ → features/ 의존 방향: features/auth/hooks/ 경로(훅)만 import (api 직접 import 금지 — architecture.md §1142-1175).
 */
export function TopNav({ onResetChat }: TopNavProps) {
  const user = useSessionStore((s) => s.user);
  const openPopup = useSessionStore((s) => s.openPopup);
  const handleLogout = useLogout();

  return (
    <header className={styles.header}>
      <LogoLink onResetChat={onResetChat} />

      <nav aria-label="주요 메뉴">
        {user === null ? (
          <button
            type="button"
            onClick={() => openPopup("email")}
            className={styles.loginBtn}
          >
            로그인
          </button>
        ) : (
          <div className={styles.userMenu}>
            <span className={styles.userEmail}>{user.email}</span>
            <button
              type="button"
              onClick={() => {
                void handleLogout();
              }}
              className={styles.logoutBtn}
            >
              로그아웃
            </button>
          </div>
        )}
      </nav>
    </header>
  );
}
