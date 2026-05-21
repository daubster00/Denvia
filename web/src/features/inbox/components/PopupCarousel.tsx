"use client";

/** PopupCarousel — Story 7.2 v2.
 *
 * 정중앙 모달 + 좌우 슬라이드 캐러셀 + dots/숫자 indicator + "오늘 하루 안보기".
 * - 노출 후보는 useActivePopups()에서 받고, "오늘 하루 안보기" 필터만 본 컴포넌트가 적용한다.
 * - X/닫기/ESC는 휘발성(컴포넌트 state)으로 처리 → 새로고침하면 다시 노출.
 *   영속 차단은 오직 "오늘 하루 안보기"(localStorage, KST 자정까지)만 수행한다.
 */

import { useEffect, useMemo, useRef, useState } from "react";

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
  top: styles.dialogTop,
  bottom: styles.dialogBottom,
  bottom_left: styles.dialogBottomLeft,
  bottom_right: styles.dialogBottomRight,
};

function safeExternalHref(raw: string | null | undefined): string | null {
  if (!raw) return null;
  const trimmed = raw.trim();
  const lower = trimmed.toLowerCase();
  if (lower.startsWith("http://") || lower.startsWith("https://")) {
    return trimmed;
  }
  return null;
}

const SWIPE_THRESHOLD_PX = 50;

export function PopupCarousel() {
  const { data: popups } = useActivePopups();
  const [closed, setClosed] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const touchStartXRef = useRef<number | null>(null);

  // "오늘 하루 안보기"만 영속 필터로 적용. X/닫기는 closed state로 휘발성 처리.
  const visiblePopups: ActivePopup[] = useMemo(() => {
    if (!popups || popups.length === 0) return [];
    return popups.filter((p) => !isDismissedForToday(p.popup_id));
  }, [popups]);

  // ESC = 닫기.
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") setClosed(true);
      if (e.key === "ArrowLeft") setActiveIndex((i) => Math.max(0, i - 1));
      if (e.key === "ArrowRight") {
        setActiveIndex((i) => Math.min(visiblePopups.length - 1, i + 1));
      }
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [visiblePopups.length]);

  if (closed || visiblePopups.length === 0) return null;

  const total = visiblePopups.length;
  const current = visiblePopups[activeIndex];
  const safeLink = safeExternalHref(current.link_url);
  const showNav = total > 1;
  // 모바일은 화면이 좁아 항상 가운데 고정 — display_position을 무시한다.
  const device = detectDevice();
  const positionClass =
    device === "mobile"
      ? styles.dialogCenter
      : POSITION_CLASS[current.display_position] ?? styles.dialogCenter;

  function handleClose() {
    setClosed(true);
  }

  function handleDismissToday() {
    visiblePopups.forEach((p) => dismissForToday(p.popup_id));
    setClosed(true);
  }

  function goPrev() {
    setActiveIndex((i) => Math.max(0, i - 1));
  }
  function goNext() {
    setActiveIndex((i) => Math.min(total - 1, i + 1));
  }

  function handleTouchStart(e: React.TouchEvent) {
    touchStartXRef.current = e.touches[0]?.clientX ?? null;
  }
  function handleTouchEnd(e: React.TouchEvent) {
    const start = touchStartXRef.current;
    touchStartXRef.current = null;
    if (start == null) return;
    const end = e.changedTouches[0]?.clientX ?? start;
    const dx = end - start;
    if (Math.abs(dx) < SWIPE_THRESHOLD_PX) return;
    if (dx > 0) goPrev();
    else goNext();
  }

  return (
    <>
      <div aria-hidden="true" className={styles.overlay} onClick={handleClose} />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="popup-carousel-title"
        className={`${styles.dialog} ${positionClass}`}
      >
        <div className={styles.header}>
          <h2 id="popup-carousel-title" className={styles.title}>
            {current.title}
          </h2>
          <button
            type="button"
            onClick={handleClose}
            aria-label="닫기"
            className={styles.closeBtn}
          >
            ✕
          </button>
        </div>

        <div
          className={styles.viewport}
          onTouchStart={handleTouchStart}
          onTouchEnd={handleTouchEnd}
        >
          {showNav && (
            <button
              type="button"
              className={`${styles.arrowBtn} ${styles.arrowBtnPrev}`}
              onClick={goPrev}
              disabled={activeIndex === 0}
              aria-label="이전 팝업"
            >
              ‹
            </button>
          )}
          <div
            className={styles.track}
            style={{ "--carousel-index": activeIndex } as React.CSSProperties}
          >
            {visiblePopups.map((p) => (
              <div key={p.popup_id} className={styles.slide}>
                {p.popup_type === "image" && p.image_url ? (
                  <div className={styles.imageSlide}>
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={p.image_url}
                      alt={p.title}
                      className={styles.image}
                    />
                  </div>
                ) : (
                  <div
                    className={styles.body}
                    dangerouslySetInnerHTML={{
                      __html: sanitizeNoticeHtml(p.body_html_safe ?? ""),
                    }}
                  />
                )}
                {safeExternalHref(p.link_url) && (
                  <div className={styles.linkRow}>
                    <a
                      href={safeExternalHref(p.link_url) ?? "#"}
                      target="_blank"
                      rel="noopener noreferrer"
                      className={styles.linkBtn}
                    >
                      자세히 보기 ↗
                    </a>
                  </div>
                )}
              </div>
            ))}
          </div>
          {showNav && (
            <button
              type="button"
              className={`${styles.arrowBtn} ${styles.arrowBtnNext}`}
              onClick={goNext}
              disabled={activeIndex === total - 1}
              aria-label="다음 팝업"
            >
              ›
            </button>
          )}
        </div>

        {showNav && (
          <div className={styles.indicator}>
            <div className={styles.dots} role="tablist" aria-label="팝업 페이지">
              {visiblePopups.map((p, i) => (
                <button
                  key={p.popup_id}
                  type="button"
                  role="tab"
                  aria-selected={i === activeIndex}
                  aria-label={`${i + 1}번째 팝업으로 이동`}
                  onClick={() => setActiveIndex(i)}
                  className={`${styles.dot} ${i === activeIndex ? styles.dotActive : ""}`}
                />
              ))}
            </div>
            <span className={styles.counter} aria-live="polite">
              {activeIndex + 1} / {total}
            </span>
          </div>
        )}

        <div className={styles.footer}>
          <button
            type="button"
            onClick={handleDismissToday}
            className={styles.footerBtn}
          >
            오늘 하루 안보기
          </button>
          <button
            type="button"
            onClick={handleClose}
            className={styles.footerBtn}
          >
            닫기
          </button>
        </div>
      </div>
    </>
  );
}
