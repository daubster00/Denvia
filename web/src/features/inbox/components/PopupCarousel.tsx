"use client";

/** PopupCarousel — Story 7.2 v2.
 *
 * 정중앙 모달 + 좌우 슬라이드 캐러셀 + dots/숫자 indicator + "오늘 하루 안보기".
 * - 노출 후보는 useActivePopups()에서 받고, 세션/하루 안보기 필터를 본 컴포넌트가 적용한다.
 * - 모달이 열리는 순간 노출된 팝업을 모두 sessionStorage에 기록 → 같은 세션에선 재노출 안 됨.
 */

import { useEffect, useMemo, useRef, useState } from "react";

import { sanitizeNoticeHtml } from "@/lib/sanitize";
import type { ActivePopup } from "../types";
import { useActivePopups } from "../hooks/useActivePopup";
import {
  dismissForToday,
  isDismissedForToday,
  isSeenInSession,
  markSeenInSession,
} from "../lib/popup-dismissal";
import styles from "./PopupCarousel.module.css";

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

  // 세션·하루 안보기 필터 적용. useMemo로 popups 변경 시에만 재계산.
  const visiblePopups: ActivePopup[] = useMemo(() => {
    if (!popups || popups.length === 0) return [];
    return popups.filter(
      (p) => !isSeenInSession(p.popup_id) && !isDismissedForToday(p.popup_id),
    );
  }, [popups]);

  // 모달이 열리는 순간(첫 마운트) 노출 후보 모두 세션에 기록.
  // 빈 배열일 땐 아무것도 안 함.
  useEffect(() => {
    if (visiblePopups.length === 0) return;
    visiblePopups.forEach((p) => markSeenInSession(p.popup_id));
    // popup id 집합이 바뀌면 다시 마킹 (예: device 변경, 새 데이터 로드).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visiblePopups.map((p) => p.popup_id).join(",")]);

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
        className={styles.dialog}
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
            style={{ transform: `translateX(-${activeIndex * 100}%)` }}
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
