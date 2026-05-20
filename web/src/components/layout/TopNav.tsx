"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { useSessionStore } from "@/stores/session-store";
import { LogoLink } from "@/components/brand/LogoLink";
import { useLogout } from "@/features/auth/hooks/useLogout";
import { useUnreadCount } from "@/features/inbox/hooks/useUnreadCount";
import { InboxPreviewDropdown } from "@/features/inbox/components/InboxPreviewDropdown";
import { MessageIcon } from "./icons/MessageIcon";
import styles from "./TopNav.module.css";

interface TopNavProps {
  onResetChat?: () => void;
}

/**
 * 상단 네비게이션 바.
 *
 * 좌측: 로고 (Story 2.5 F-306 onResetChat 트리거).
 * 우측 — 비로그인: "로그인" 버튼.
 *      - 로그인: 쪽지함 → 계정 토글(플랜 원 + 이메일 + ▶) → 드롭다운(현재 플랜·계정 / 마이페이지 / 로그아웃).
 */
export function TopNav({ onResetChat }: TopNavProps) {
  const user = useSessionStore((s) => s.user);
  const openPopup = useSessionStore((s) => s.openPopup);
  const handleLogout = useLogout();
  const pathname = usePathname();
  const { data: unread } = useUnreadCount();
  const unreadCount = unread?.unread_count ?? 0;

  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    const onPointerDown = (e: MouseEvent | TouchEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMenuOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [menuOpen]);

  const isPro = user?.subscription_status === "pro";
  const planLabel = isPro ? "Pro" : "Basic";
  const planClass = isPro ? styles.planBadgePro : styles.planBadgeFree;
  const planIconSrc = isPro
    ? "/symbol_no_background_color.png"
    : "/symbol_no_background_gray.png";

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
            <div className={styles.inboxIconWrap}>
              <Link
                href="/inbox"
                aria-label="쪽지함"
                className={styles.iconBtn}
                aria-current={pathname === "/inbox" ? "page" : undefined}
              >
                <MessageIcon aria-hidden="true" />
                {unreadCount > 0 && (
                  <span
                    className={styles.unreadBadge}
                    role="status"
                    aria-live="polite"
                    aria-label={`안 읽은 쪽지 ${unreadCount}개`}
                  >
                    {unreadCount > 9 ? "9+" : unreadCount}
                  </span>
                )}
              </Link>
              <InboxPreviewDropdown />
            </div>

            <div ref={menuRef} className={styles.accountWrapper}>
              <button
                type="button"
                className={styles.accountBtn}
                aria-haspopup="menu"
                aria-expanded={menuOpen}
                aria-label={`${user.email} 계정 메뉴`}
                onClick={() => setMenuOpen((v) => !v)}
              >
                <span
                  className={`${styles.planBadge} ${planClass}`}
                  aria-label={`${planLabel} 플랜`}
                >
                  <Image
                    src={planIconSrc}
                    alt=""
                    width={20}
                    height={20}
                    className={styles.planBadgeIcon}
                  />
                </span>
                <span className={styles.userEmail}>{user.email}</span>
                <svg
                  className={`${styles.chevron} ${menuOpen ? styles.chevronOpen : ""}`}
                  viewBox="0 0 12 12"
                  width={12}
                  height={12}
                  aria-hidden="true"
                >
                  <path
                    d="M4 2 L8 6 L4 10"
                    stroke="currentColor"
                    strokeWidth={1.6}
                    fill="none"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </button>

              {menuOpen && (
                <div className={styles.menuPanel} role="menu">
                  <div className={styles.menuPlanGroup}>
                    <div className={styles.menuPlanLabel}>현재 플랜</div>
                    <div className={styles.menuPlanRow}>
                      <span
                        className={`${styles.planBadge} ${planClass}`}
                        aria-hidden="true"
                      >
                        <Image
                          src={planIconSrc}
                          alt=""
                          width={20}
                          height={20}
                          className={styles.planBadgeIcon}
                        />
                      </span>
                      <span className={styles.menuPlanName}>{planLabel}</span>
                    </div>
                    <div className={styles.menuAccount}>{user.email}</div>
                  </div>

                  <Link
                    href="/my"
                    role="menuitem"
                    className={styles.menuItem}
                    aria-current={pathname === "/my" ? "page" : undefined}
                    onClick={() => setMenuOpen(false)}
                  >
                    마이페이지
                  </Link>
                  <Link
                    href="/my/profile"
                    role="menuitem"
                    className={styles.menuItem}
                    aria-current={pathname === "/my/profile" ? "page" : undefined}
                    onClick={() => setMenuOpen(false)}
                  >
                    회원정보
                  </Link>
                  <button
                    type="button"
                    role="menuitem"
                    className={styles.menuItem}
                    onClick={() => {
                      setMenuOpen(false);
                      void handleLogout();
                    }}
                  >
                    로그아웃
                  </button>
                </div>
              )}
            </div>
          </div>
        )}
      </nav>
    </header>
  );
}
