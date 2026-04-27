"use client";

import Image from "next/image";
import Link from "next/link";

interface LogoLinkProps {
  /** F-306 로고 클릭 시 채팅 초기화 훅 — Epic 2에서 구현 */
  onResetChat?: () => void;
}

/** Denvia 로고 링크 — 좌측 상단 배치, 채팅 컨텍스트에서 onResetChat 연결 (F-306) */
export function LogoLink({ onResetChat }: LogoLinkProps) {
  const ariaLabel = onResetChat ? "대화 초기화 및 홈으로" : "Denvia 홈";

  return (
    <Link
      href="/"
      aria-label={ariaLabel}
      onClick={() => onResetChat?.()}
      style={{ display: "flex", alignItems: "center", textDecoration: "none" }}
    >
      <Image
        src="/logo-full.png"
        alt="Denvia"
        width={916}
        height={269}
        priority
        style={{ height: 36, width: "auto" }}
      />
    </Link>
  );
}
