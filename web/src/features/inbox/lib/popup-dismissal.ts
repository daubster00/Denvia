/** 팝업 노출 제어 — Story 7.2 v2.
 *
 * 영속 차단은 "오늘 하루 안보기"(localStorage, KST 자정까지)만 처리.
 * X/닫기/ESC 같은 일반 닫기는 컴포넌트 state에서만 휘발성으로 다루어
 * 새로고침하면 다시 노출되도록 한다.
 *
 * 서버는 후보 배열만 내려주고, 실제 노출 여부는 본 헬퍼들이 결정한다.
 */

const DISMISS_PREFIX = "popup_dismissed_until_";

function safeWindow(): Window | null {
  if (typeof window === "undefined") return null;
  return window;
}

/** 한국 시간 기준 다음날 00:00의 ISO 문자열을 반환. */
export function nextKstMidnightIso(now: Date = new Date()): string {
  // KST = UTC+9. UTC 기준으로 환산해 자정을 잡는다.
  const kstNow = new Date(now.getTime() + 9 * 60 * 60 * 1000);
  // 다음 날 자정(KST) UTC 표현
  const kstTomorrow = new Date(
    Date.UTC(
      kstNow.getUTCFullYear(),
      kstNow.getUTCMonth(),
      kstNow.getUTCDate() + 1,
      0,
      0,
      0,
      0,
    ),
  );
  // KST 자정 → UTC 시점은 9시간 전
  const utcAtKstMidnight = new Date(kstTomorrow.getTime() - 9 * 60 * 60 * 1000);
  return utcAtKstMidnight.toISOString();
}

export function dismissForToday(popupId: number, now: Date = new Date()): void {
  const w = safeWindow();
  if (!w) return;
  try {
    w.localStorage.setItem(
      `${DISMISS_PREFIX}${popupId}`,
      nextKstMidnightIso(now),
    );
  } catch {
    // 무시.
  }
}

export function isDismissedForToday(
  popupId: number,
  now: Date = new Date(),
): boolean {
  const w = safeWindow();
  if (!w) return false;
  try {
    const raw = w.localStorage.getItem(`${DISMISS_PREFIX}${popupId}`);
    if (!raw) return false;
    const expireAt = new Date(raw);
    if (Number.isNaN(expireAt.getTime())) return false;
    if (expireAt.getTime() <= now.getTime()) {
      // 만료된 항목은 청소.
      w.localStorage.removeItem(`${DISMISS_PREFIX}${popupId}`);
      return false;
    }
    return true;
  } catch {
    return false;
  }
}

/** SSR 안전 디바이스 감지 — 클라이언트 마운트 후에만 정확. */
export function detectDevice(): "pc" | "mobile" {
  const w = safeWindow();
  if (!w) return "pc";
  return w.matchMedia("(max-width: 768px)").matches ? "mobile" : "pc";
}
