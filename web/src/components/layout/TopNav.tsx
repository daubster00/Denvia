"use client";

import { useSessionStore } from "@/stores/session-store";
import { LogoLink } from "@/components/brand/LogoLink";

interface TopNavProps {
  onResetChat?: () => void;
}

/**
 * 상단 네비게이션 바.
 * 좌측: 로고 / 우측: 로그인 버튼 (비로그인 상태).
 * components/ → features/ 참조 금지 (store 메서드로만 트리거).
 */
export function TopNav({ onResetChat }: TopNavProps) {
  const openPopup = useSessionStore((s) => s.openPopup);

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
        <button
          type="button"
          onClick={() => openPopup("email")}
          style={{
            padding: "8px 20px",
            background: "linear-gradient(135deg, #8B5CF6 0%, #D946EF 100%)",
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
      </nav>

      <style>{`
        @media (max-width: 767px) {
          header { height: 56px !important; padding: 0 16px !important; }
        }
      `}</style>
    </header>
  );
}
