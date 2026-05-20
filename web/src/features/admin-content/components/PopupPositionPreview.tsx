"use client";

/**
 * 팝업 미리보기 — 실제 사용자 페이지에서 노출되는 형식·위치를 그대로 보여준다.
 * - `display_position`에 따라 가상의 데스크톱 뷰포트 안에서 다이얼로그 위치를 결정.
 * - 모바일은 화면이 좁아 항상 가운데 (PopupCarousel과 동일 규칙).
 * - `target_device`가 "both"이면 PC/모바일 탭 전환 가능.
 */

import { useState } from "react";

import type { PopupFormInput } from "@/features/admin-content/api/popup";
import { resolveAssetUrl } from "@/lib/asset-url";
import { sanitizeNoticeHtml } from "@/lib/sanitize";

import styles from "./PopupPositionPreview.module.css";

interface Props {
  form: PopupFormInput;
}

type DeviceView = "pc" | "mobile";

const POSITION_CLASS: Record<PopupFormInput["display_position"], string> = {
  center: styles.dialogCenter,
  top: styles.dialogTop,
  bottom: styles.dialogBottom,
  bottom_left: styles.dialogBottomLeft,
  bottom_right: styles.dialogBottomRight,
};

const SAFE_HREF_RX = /^https?:\/\//i;

export function PopupPositionPreview({ form }: Props) {
  const canShowPc = form.target_device !== "mobile";
  const canShowMobile = form.target_device !== "pc";
  const initialDevice: DeviceView = canShowPc ? "pc" : "mobile";
  const [device, setDevice] = useState<DeviceView>(initialDevice);

  // 모바일은 항상 가운데(좁은 화면 규칙). PopupCarousel과 동일 동작.
  const positionClass =
    device === "mobile"
      ? styles.dialogCenter
      : POSITION_CLASS[form.display_position] ?? styles.dialogCenter;

  const safeHref =
    form.link_url && SAFE_HREF_RX.test(form.link_url) ? form.link_url : null;

  const isImageType = form.popup_type === "image" && Boolean(form.image_url);
  const safeBodyHtml = sanitizeNoticeHtml(form.body_html ?? "");

  return (
    <div className={styles.root} aria-label="팝업 미리보기">
      {canShowPc && canShowMobile ? (
        <div role="tablist" aria-label="디바이스 선택" className={styles.deviceTabs}>
          <button
            type="button"
            role="tab"
            aria-selected={device === "pc"}
            className={`${styles.deviceTab} ${
              device === "pc" ? styles.deviceTabActive : ""
            }`}
            onClick={() => setDevice("pc")}
          >
            PC
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={device === "mobile"}
            className={`${styles.deviceTab} ${
              device === "mobile" ? styles.deviceTabActive : ""
            }`}
            onClick={() => setDevice("mobile")}
          >
            모바일
          </button>
        </div>
      ) : null}

      <p className={styles.note}>
        실제 사용자 페이지에서 보이는 모습과 위치입니다.
        {device === "mobile"
          ? " 모바일은 화면이 좁아 위치 설정과 무관하게 항상 가운데에 표시됩니다."
          : null}
      </p>

      <div
        className={
          device === "pc" ? styles.viewportPc : styles.viewportMobile
        }
      >
        <div className={styles.viewportBar}>
          <span className={styles.viewportDot} />
          <span className={styles.viewportDot} />
          <span className={styles.viewportDot} />
          <span className={styles.viewportLabel}>
            {device === "pc" ? "데스크톱 화면" : "모바일 화면"}
          </span>
        </div>
        <div className={styles.viewportStage}>
          <div className={styles.pageMock}>
            <div className={styles.pageMockHeader} />
            <div className={styles.pageMockBlock} />
            <div className={styles.pageMockBlockNarrow} />
            <div className={styles.pageMockBlock} />
          </div>
          <div className={styles.overlay} aria-hidden="true" />
          <div
            className={`${styles.dialog} ${positionClass}`}
            role="presentation"
          >
            <div className={styles.dialogHeader}>
              <h4 className={styles.dialogTitle}>
                {form.title || "(제목 미입력)"}
              </h4>
              <span className={styles.dialogCloseMock} aria-hidden="true">
                ✕
              </span>
            </div>
            <div className={styles.dialogContent}>
              {isImageType ? (
                <div className={styles.imageSlide}>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={resolveAssetUrl(form.image_url ?? "")}
                    alt={form.title}
                    className={styles.image}
                  />
                </div>
              ) : (
                <div
                  className={styles.dialogBody}
                  // 서버 nh3 + 클라이언트 DOMPurify 2중 필터 거친 안전 HTML.
                  dangerouslySetInnerHTML={{ __html: safeBodyHtml }}
                />
              )}
              {safeHref ? (
                <div className={styles.linkRow}>
                  <span className={styles.linkBtn}>자세히 보기 ↗</span>
                </div>
              ) : null}
            </div>
            <div className={styles.dialogFooter}>
              <span className={styles.footerBtn}>오늘 하루 안보기</span>
              <span className={styles.footerBtn}>닫기</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
