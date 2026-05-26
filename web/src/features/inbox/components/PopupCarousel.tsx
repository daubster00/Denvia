"use client";

/** PopupCarousel — 다중 팝업 동시 표시.
 *
 * 종전 슬라이드 캐러셀 폐기 → 활성 팝업을 각자 독립 다이얼로그로 동시에 렌더.
 * - PC: 각 팝업이 자신의 display_position(center/left/right/custom) 그대로 표시.
 *   center 가 여러 개면 인덱스 기준 cascading offset 으로 살짝씩 어긋나게 배치.
 * - 모바일: 좁아서 항상 가운데. 다수일 때 cascading offset 으로 겹침 완화.
 * - 오버레이 없음 — 각 팝업은 우상단 X 또는 "오늘 하루 안보기"로 개별 종료.
 *   ESC 는 화면의 모든 팝업을 한 번에 닫는다(휘발성).
 * - "오늘 하루 안보기"는 해당 팝업만 localStorage 에 KST 자정까지 차단.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import { sanitizeNoticeHtml } from "@/lib/sanitize";
import type { ActivePopup, PopupDisplayPosition } from "../types";
import { useActivePopups } from "../hooks/useActivePopup";
import {
  detectDevice,
  dismissForToday,
  isDismissedForToday,
} from "../lib/popup-dismissal";
import styles from "./PopupCarousel.module.css";

const POSITION_CLASS: Record<PopupDisplayPosition, string> = {
  center: styles.dialogCenter,
  left: styles.dialogLeft,
  right: styles.dialogRight,
  custom: styles.dialogCustom,
};

const CASCADE_OFFSET_PX = 24;

function safeExternalHref(raw: string | null | undefined): string | null {
  if (!raw) return null;
  const trimmed = raw.trim();
  const lower = trimmed.toLowerCase();
  if (lower.startsWith("http://") || lower.startsWith("https://")) {
    return trimmed;
  }
  return null;
}

export function PopupCarousel() {
  const { data: popups } = useActivePopups();
  const [closedIds, setClosedIds] = useState<Set<number>>(new Set());

  const visiblePopups: ActivePopup[] = useMemo(() => {
    if (!popups || popups.length === 0) return [];
    return popups.filter(
      (p) => !isDismissedForToday(p.popup_id) && !closedIds.has(p.popup_id),
    );
  }, [popups, closedIds]);

  const closeOne = useCallback((popupId: number) => {
    setClosedIds((prev) => {
      const next = new Set(prev);
      next.add(popupId);
      return next;
    });
  }, []);

  const closeAll = useCallback(() => {
    if (visiblePopups.length === 0) return;
    setClosedIds((prev) => {
      const next = new Set(prev);
      visiblePopups.forEach((p) => next.add(p.popup_id));
      return next;
    });
  }, [visiblePopups]);

  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") closeAll();
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [closeAll]);

  if (visiblePopups.length === 0) return null;

  return (
    <>
      {visiblePopups.map((popup, index) => (
        <PopupDialog
          key={popup.popup_id}
          popup={popup}
          cascadeIndex={index}
          onClose={() => closeOne(popup.popup_id)}
          onDismissToday={() => {
            dismissForToday(popup.popup_id);
            closeOne(popup.popup_id);
          }}
        />
      ))}
    </>
  );
}

interface PopupDialogProps {
  popup: ActivePopup;
  cascadeIndex: number;
  onClose: () => void;
  onDismissToday: () => void;
}

function PopupDialog({
  popup,
  cascadeIndex,
  onClose,
  onDismissToday,
}: PopupDialogProps) {
  const device = detectDevice();
  // 모바일은 좁아 항상 가운데 고정 — display_position 무시.
  const positionClass =
    device === "mobile"
      ? styles.dialogCenter
      : POSITION_CLASS[popup.display_position] ?? styles.dialogCenter;

  // cascading offset: 같은 위치에 여러 팝업이 겹치는 경우를 위한 시각적 분산.
  // custom 좌표는 그대로 두고, 그 외 위치 모드에만 적용.
  const cascade = cascadeIndex * CASCADE_OFFSET_PX;

  const dialogStyle: React.CSSProperties = {};
  if (device !== "mobile" && popup.display_position === "custom") {
    dialogStyle["--popup-top-px" as keyof React.CSSProperties] =
      `${popup.display_position_top_px ?? 0}px` as never;
    dialogStyle["--popup-left-px" as keyof React.CSSProperties] =
      `${popup.display_position_left_px ?? 0}px` as never;
  } else if (cascade > 0) {
    dialogStyle["--popup-cascade-px" as keyof React.CSSProperties] =
      `${cascade}px` as never;
  }

  const safeLink = safeExternalHref(popup.link_url);

  return (
    <div
      role="dialog"
      aria-modal="false"
      aria-labelledby={`popup-title-${popup.popup_id}`}
      className={`${styles.dialog} ${positionClass}`}
      style={dialogStyle}
    >
      <div className={styles.header}>
        <h2 id={`popup-title-${popup.popup_id}`} className={styles.title}>
          {popup.title}
        </h2>
        <button
          type="button"
          onClick={onClose}
          aria-label="닫기"
          className={styles.closeBtn}
        >
          ✕
        </button>
      </div>

      <div className={styles.viewport}>
        {popup.popup_type === "image" && popup.image_url ? (
          <div className={styles.imageSlide}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={popup.image_url}
              alt={popup.title}
              className={styles.image}
            />
          </div>
        ) : (
          <div
            className={styles.body}
            dangerouslySetInnerHTML={{
              __html: sanitizeNoticeHtml(popup.body_html_safe ?? ""),
            }}
          />
        )}
        {safeLink && (
          <div className={styles.linkRow}>
            <a
              href={safeLink}
              target="_blank"
              rel="noopener noreferrer"
              className={styles.linkBtn}
            >
              자세히 보기 ↗
            </a>
          </div>
        )}
      </div>

      <div className={styles.footer}>
        <button
          type="button"
          onClick={onDismissToday}
          className={styles.footerBtn}
        >
          오늘 하루 안보기
        </button>
        <button type="button" onClick={onClose} className={styles.footerBtn}>
          닫기
        </button>
      </div>
    </div>
  );
}
