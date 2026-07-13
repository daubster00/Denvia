/** #130 ① — 질문 전송 안내 팝업의 "오늘 하루 보지 않기" 처리.
 *
 * 문구가 관리자에 의해 바뀌더라도 차단은 단순 하루 기준(KST 자정 리셋)이다.
 * 그래서 고정 문자열 키(`qa_notice`) 하나만 사용한다.
 *
 * inbox 팝업(popup-dismissal.ts)의 KST 자정 계산 규칙을 그대로 재사용해
 * 자정 리셋 로직 드리프트를 막는다.
 */

import { nextKstMidnightIso } from "@/features/inbox/lib/popup-dismissal";

const DISMISS_KEY = "qa_notice_dismissed_until";

function safeWindow(): Window | null {
  if (typeof window === "undefined") return null;
  return window;
}

/** "오늘 하루 보지 않기" — KST 자정까지 차단 시각을 localStorage에 기록. */
export function dismissQaNoticeForToday(now: Date = new Date()): void {
  const w = safeWindow();
  if (!w) return;
  try {
    w.localStorage.setItem(DISMISS_KEY, nextKstMidnightIso(now));
  } catch {
    // 무시.
  }
}

/** 오늘(KST) 차단되어 있으면 true. 만료된 항목은 청소한다. */
export function isQaNoticeDismissedForToday(now: Date = new Date()): boolean {
  const w = safeWindow();
  if (!w) return false;
  try {
    const raw = w.localStorage.getItem(DISMISS_KEY);
    if (!raw) return false;
    const expireAt = new Date(raw);
    if (Number.isNaN(expireAt.getTime())) return false;
    if (expireAt.getTime() <= now.getTime()) {
      w.localStorage.removeItem(DISMISS_KEY);
      return false;
    }
    return true;
  } catch {
    return false;
  }
}
