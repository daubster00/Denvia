"use client";

import Image from "next/image";
import Link from "next/link";

interface LogoLinkProps {
  /** F-306 로고 클릭 시 채팅 초기화 훅 — Epic 2에서 구현 */
  onResetChat?: () => void;
}

/** Denvia 로고 링크 — 좌측 상단 배치, 클릭 시 onResetChat 자리만 준비 (Epic 2) */
export function LogoLink({ onResetChat }: LogoLinkProps) {
  return (
    <Link
      href="/"
      aria-label="Denvia 홈"
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
