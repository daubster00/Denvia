"use client";

import { useState } from "react";
import { usePathname } from "next/navigation";
import Link from "next/link";
import {
  IconApps,
  IconPersons,
  IconCircleBlock,
  IconDocument,
  IconStorage,
  IconCoins,
  IconBubble,
  IconSetting,
  IconWrite,
  IconChevronRight,
} from "@wanteddev/wds-icon";
import { useAdminSessionStore } from "@/stores/admin-session-store";
import { canAccessAdminPath } from "@/features/admin-auth/pageAccess";
import styles from "./AdminSidebar.module.css";

type IconComponent = React.ComponentType<React.SVGProps<SVGSVGElement>>;

interface SubMenuItem {
  label: string;
  href: string;
}

interface MenuItem {
  icon: IconComponent;
  label: string;
  href: string;
  children?: SubMenuItem[];
}

const MENU_ITEMS: MenuItem[] = [
  { icon: IconApps as IconComponent, label: "대시보드", href: "/admin" },
  { icon: IconPersons as IconComponent, label: "고객관리", href: "/admin/users" },
  {
    icon: IconCircleBlock as IconComponent,
    label: "이상탐지",
    href: "/admin/anomaly",
    children: [
      { label: "이상 이벤트", href: "/admin/anomaly" },
      { label: "주의 계정", href: "/admin/anomaly/watched" },
      { label: "탐지 기준 설정", href: "/admin/anomaly/thresholds" },
    ],
  },
  {
    icon: IconDocument as IconComponent,
    label: "콘텐츠",
    href: "/admin/content",
    children: [
      { label: "서비스 토글", href: "/admin/content" },
      { label: "팝업 관리", href: "/admin/content/popups" },
      { label: "공지(쪽지) 관리", href: "/admin/content/notices" },
    ],
  },
  {
    icon: IconStorage as IconComponent,
    label: "RAG 데이터 관리",
    href: "/admin/rag",
    children: [
      { label: "동의어", href: "/admin/synonyms" },
      { label: "코드소스", href: "/admin/rag" },
      { label: "프롬프트", href: "/admin/prompt" },
    ],
  },
  {
    icon: IconCoins as IconComponent,
    label: "재무",
    href: "/admin/finance",
    children: [
      { label: "결제 기록", href: "/admin/finance/payments" },
      { label: "매출 대시보드", href: "/admin/finance/revenue" },
      { label: "비상 정지", href: "/admin/finance/killswitch" },
    ],
  },
  {
    icon: IconBubble as IconComponent,
    label: "CS",
    href: "/admin/cs",
    children: [
      { label: "문의 관리", href: "/admin/cs" },
      { label: "휴지통", href: "/admin/cs/trash" },
    ],
  },
  { icon: IconWrite as IconComponent, label: "수정요청", href: "/admin/board" },
  // master/operator 만 보이는 항목. sub_operator 가 클릭해도 백엔드 403.
  // children: 관리자 목록 / 등급 관리 / 페이지 권한 / 활동 로그.
  // 권한 매트릭스 수정도 master/operator 동일(2026-05-28 SSOT 갱신).
  {
    icon: IconPersons as IconComponent,
    label: "관리자 관리",
    href: "/admin/admins",
    children: [
      { label: "관리자 목록", href: "/admin/admins" },
      { label: "등급 관리", href: "/admin/admins/grades" },
      { label: "페이지 권한", href: "/admin/admins/permissions" },
      { label: "활동 로그", href: "/admin/admins/logs" },
    ],
  },
  // Story 4.6 — 운영 가시성 확장. children 없는 단일 페이지.
  { icon: IconBubble as IconComponent, label: "알림톡 관리", href: "/admin/alimtalk" },
  {
    icon: IconSetting as IconComponent,
    label: "설정",
    href: "/admin/settings",
    children: [
      { label: "예산 · AI 모델", href: "/admin/settings" },
      { label: "SEO", href: "/admin/settings/seo" },
      { label: "결제(PG) 키", href: "/admin/settings/payment" },
    ],
  },
];

function cx(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(" ");
}

function isHrefActive(pathname: string, href: string): boolean {
  if (href === "/admin") return pathname === "/admin";
  return pathname === href || pathname.startsWith(`${href}/`);
}

function isSubItemActive(pathname: string, href: string, parentHref: string): boolean {
  // 서브가 부모와 정확히 같은 URL이면 정확 매칭만 (다른 서브 활성 시 부모 서브가 같이 빛나는 것 방지)
  if (href === parentHref) return pathname === href;
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function AdminSidebar() {
  const pathname = usePathname();
  const admin = useAdminSessionStore((s) => s.admin);
  const [isTabletExpanded, setIsTabletExpanded] = useState(false);
  const [hoveredHref, setHoveredHref] = useState<string | null>(null);

  const isActive = (href: string) => isHrefActive(pathname, href);

  // 본 관리자 권한으로 접근 불가한 항목은 사이드바에서 숨긴다.
  // children 이 있으면, 접근 가능한 child 가 하나라도 있을 때만 부모를 노출.
  const visibleItems = MENU_ITEMS.flatMap((item) => {
    const children = item.children;
    if (children && children.length > 0) {
      const visibleChildren = children.filter((c) => canAccessAdminPath(c.href, admin));
      if (visibleChildren.length === 0) return [];
      return [{ ...item, children: visibleChildren }];
    }
    return canAccessAdminPath(item.href, admin) ? [item] : [];
  });

  return (
    <>
      {isTabletExpanded && (
        <div
          className={styles.backdrop}
          onClick={() => setIsTabletExpanded(false)}
          aria-hidden="true"
        />
      )}

      <nav
        aria-label="관리자 메뉴"
        className={cx(styles.sidebar, isTabletExpanded && styles.sidebarExpanded)}
      >
        <div className={styles.brand}>
          <span className={styles.brandMark} aria-hidden="true" />
          <span className={styles.brandText}>관리자 콘솔</span>
        </div>

        <div className={styles.toggleRow}>
          <button
            type="button"
            className={styles.toggleButton}
            onClick={() => setIsTabletExpanded((v) => !v)}
            aria-label={isTabletExpanded ? "메뉴 닫기" : "메뉴 펼치기"}
            aria-expanded={isTabletExpanded}
          >
            <span
              className={cx(
                styles.toggleIcon,
                isTabletExpanded && styles.toggleIconRotated,
              )}
            >
              <IconChevronRight width="1.125rem" height="1.125rem" />
            </span>
          </button>
        </div>

        <ul className={styles.menu}>
          {visibleItems.map((item) => {
            const { icon: Icon, label, href, children } = item;
            const hasChildren = !!children && children.length > 0;
            const childActive =
              hasChildren && children!.some((c) => isHrefActive(pathname, c.href));
            const active = isActive(href) || childActive;
            const isHovered = hoveredHref === href;
            // 현재 라우트가 이 부모 밑에 있을 때만 펼침 (호버 시 미리보기 허용)
            const isExpanded = hasChildren && (active || isHovered);

            return (
              <li
                key={href}
                className={styles.menuLi}
                onMouseEnter={hasChildren ? () => setHoveredHref(href) : undefined}
                onMouseLeave={hasChildren ? () => setHoveredHref(null) : undefined}
              >
                <Link
                  href={href}
                  aria-current={active && !hasChildren ? "page" : undefined}
                  aria-expanded={hasChildren ? isExpanded : undefined}
                  className={cx(
                    styles.menuItem,
                    active && !hasChildren && styles.menuItemActive,
                    hasChildren && active && styles.menuItemParentActive,
                  )}
                >
                  <span className={styles.menuIcon}>
                    <Icon width="1.25rem" height="1.25rem" />
                  </span>
                  <span className={styles.menuLabel}>{label}</span>
                  {hasChildren && (
                    <span
                      className={cx(
                        styles.caret,
                        isExpanded && styles.caretExpanded,
                      )}
                      aria-hidden="true"
                    >
                      <IconChevronRight width="0.875rem" height="0.875rem" />
                    </span>
                  )}
                </Link>

                {hasChildren && (
                  <div
                    className={cx(
                      styles.subMenuWrap,
                      isExpanded && styles.subMenuWrapOpen,
                    )}
                  >
                    <ul className={styles.subMenu}>
                      {children!.map((sub) => {
                        const subActive = isSubItemActive(pathname, sub.href, href);
                        return (
                          <li key={sub.href}>
                            <Link
                              href={sub.href}
                              aria-current={subActive ? "page" : undefined}
                              className={cx(
                                styles.subMenuItem,
                                subActive && styles.subMenuItemActive,
                              )}
                            >
                              <span className={styles.subMenuDot} aria-hidden="true" />
                              <span className={styles.subMenuLabel}>{sub.label}</span>
                            </Link>
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                )}
              </li>
            );
          })}
        </ul>

        <div className={styles.footer}>Denvia Admin v1</div>
      </nav>
    </>
  );
}
