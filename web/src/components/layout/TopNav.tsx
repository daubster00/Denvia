"use client";

import { useSessionStore } from "@/stores/session-store";
import { LogoLink } from "@/components/brand/LogoLink";
import { useLogout } from "@/features/auth/hooks/useLogout";

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
    <header
      style={{
        position: "sticky",
        top: 0,
        zIndex: 100,
        backgroundColor: "#fff",
        borderBottom: "1px solid #E1E2E4",
        height: "var(--topnav-height, 64px)",
        display: "flex",
        alignItems: "center",
        padding: "0 24px",
        justifyContent: "space-between",
      }}
    >
      <LogoLink onResetChat={onResetChat} />

      <nav aria-label="주요 메뉴">
        {user === null ? (
          <button
            type="button"
            onClick={() => openPopup("email")}
            style={{
              padding: "8px 20px",
              background:
                "linear-gradient(135deg, #8B5CF6 0%, #D946EF 100%)",
              color: "#fff",
              border: "none",
              borderRadius: 8,
              fontSize: 14,
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            로그인
          </button>
        ) : (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 12,
            }}
          >
            <span
              style={{
                fontSize: 14,
                color: "#5A5C63",
                maxWidth: 200,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {user.email}
            </span>
            <button
              type="button"
              onClick={() => {
                void handleLogout();
              }}
              style={{
                padding: "8px 16px",
                background: "transparent",
                color: "#5A5C63",
                border: "1px solid #E1E2E4",
                borderRadius: 8,
                fontSize: 13,
                fontWeight: 500,
                cursor: "pointer",
              }}
            >
              로그아웃
            </button>
          </div>
        )}
      </nav>

      <style>{`
        @media (max-width: 767px) {
          header { height: 56px !important; padding: 0 16px !important; }
        }
      `}</style>
    </header>
  );
}
