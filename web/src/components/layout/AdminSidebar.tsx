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
  IconCode,
  IconCoins,
  IconBubble,
  IconSetting,
  IconChevronRight,
} from "@wanteddev/wds-icon";
import styles from "./AdminSidebar.module.css";

type IconComponent = React.ComponentType<React.SVGProps<SVGSVGElement>>;

interface MenuItem {
  icon: IconComponent;
  label: string;
  href: string;
}

const MENU_ITEMS: MenuItem[] = [
  { icon: IconApps as IconComponent, label: "대시보드", href: "/admin" },
  { icon: IconPersons as IconComponent, label: "고객관리", href: "/admin/users" },
  { icon: IconCircleBlock as IconComponent, label: "이상탐지", href: "/admin/anomaly" },
  { icon: IconDocument as IconComponent, label: "콘텐츠", href: "/admin/content" },
  { icon: IconStorage as IconComponent, label: "RAG 데이터", href: "/admin/rag" },
  { icon: IconCode as IconComponent, label: "프롬프트", href: "/admin/prompt" },
  { icon: IconCoins as IconComponent, label: "재무", href: "/admin/finance" },
  { icon: IconBubble as IconComponent, label: "CS", href: "/admin/cs" },
  { icon: IconSetting as IconComponent, label: "설정", href: "/admin/settings" },
];

function cx(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(" ");
}

export function AdminSidebar() {
  const pathname = usePathname();
  const [isTabletExpanded, setIsTabletExpanded] = useState(false);

  const isActive = (href: string) =>
    href === "/admin" ? pathname === "/admin" : pathname.startsWith(href);

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
          {MENU_ITEMS.map(({ icon: Icon, label, href }) => {
            const active = isActive(href);
            return (
              <li key={href}>
                <Link
                  href={href}
                  aria-current={active ? "page" : undefined}
                  className={cx(styles.menuItem, active && styles.menuItemActive)}
                >
                  <span className={styles.menuIcon}>
                    <Icon width="1.25rem" height="1.25rem" />
                  </span>
                  <span className={styles.menuLabel}>{label}</span>
                </Link>
              </li>
            );
          })}
        </ul>

        <div className={styles.footer}>Denvia Admin v1</div>
      </nav>
    </>
  );
}
