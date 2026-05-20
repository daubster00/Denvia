/**
 * 전체 시스템 KRW 표기 통일 — UI 표시 전용 유틸.
 *
 * DB·API의 USD 원본 필드는 그대로 유지(OpenAI 청구는 USD)하고, 화면에 표시할 때만
 * KRW 환산값을 사용한다. 응답에 이미 KRW 환산 필드(`*_krw`)가 포함된 경우 그 값을
 * 그대로 쓰고, 환산 보조 필드가 없는 historical 데이터는 `usd_to_krw` 환율로 계산한다.
 */

const KRW_FORMATTER = new Intl.NumberFormat("ko-KR");

/**
 * 정수(원) 값을 "₩1,234,567" 형식으로 포맷한다.
 */
export function formatKRW(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const num = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(num)) return "—";
  return `₩${KRW_FORMATTER.format(Math.round(num))}`;
}

/**
 * USD 값(string | number)을 환율로 환산해 KRW 정수(원)로 반환.
 * 응답에 *_krw 필드가 없는 historical/legacy 데이터 변환용.
 */
export function usdToKrwInt(
  usd: number | string,
  usdToKrw: number,
): number {
  const u = typeof usd === "number" ? usd : Number(usd);
  if (!Number.isFinite(u)) return 0;
  return Math.round(u * usdToKrw);
}

/**
 * USD 값을 환율로 환산해 "₩1,234,567" 형식으로 표기.
 */
export function formatKRWFromUSD(
  usd: number | string,
  usdToKrw: number,
): string {
  return formatKRW(usdToKrwInt(usd, usdToKrw));
}
