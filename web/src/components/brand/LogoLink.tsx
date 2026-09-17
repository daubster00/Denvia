"use client";

import Image from "next/image";
import Link from "next/link";
import styles from "./LogoLink.module.css";

interface LogoLinkProps {
  /** F-306 로고 클릭 시 채팅 초기화 훅 — Epic 2에서 구현 */
  onResetChat?: () => void;
  /** 클릭 시 이동할 경로 override (예: 관리자 영역 → /admin). 미지정 시 "/" */
  href?: string;
  /** 접근성 라벨 override */
  ariaLabel?: string;
}

/** Denvia 로고 링크 — 좌측 상단 배치, 채팅 컨텍스트에서 onResetChat 연결 (F-306) */
export function LogoLink({ onResetChat, href, ariaLabel }: LogoLinkProps) {
  const isResetLink = onResetChat != null;
  const resolvedHref = href ?? "/";
  const resolvedAriaLabel =
    ariaLabel ?? (isResetLink ? "대화 초기화 및 홈으로" : "Denvia 홈");

  return (
    <Link
      href={resolvedHref}
      aria-label={resolvedAriaLabel}
      onClick={() => {
        if (isResetLink) {
          onResetChat();
        }
      }}
      className={styles.link}
    >
      {/* unoptimized: /_next/image 변환 캐시가 특정 키에서 무한 대기에 빠져 로고가
          전면 미표시된 사고(2026-09-17)가 있었다. 49KB 원본을 그대로 내보내
          이미지 최적화 경로 자체를 타지 않게 한다. */}
      <Image
        src="/logo-full.png"
        alt="Denvia"
        width={916}
        height={269}
        priority
        unoptimized
        className={styles.image}
      />
    </Link>
  );
}
