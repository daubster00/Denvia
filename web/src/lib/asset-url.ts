/**
 * 백엔드 정적 자산 URL 처리 헬퍼.
 *
 * 백엔드는 업로드된 이미지를 `/static/popup-images/...`, `/static/support-reply-images/...`
 * 같은 상대 경로로 응답한다. 그러나 웹앱(Next.js)과 API 서버의 origin이 분리되어 있어
 * (개발: `:3000` vs `:8000`) 상대 경로 `<img src="/static/...">`는 웹앱 origin으로
 * 해석돼 이미지를 불러오지 못한다.
 *
 * 이 헬퍼는 상대 `/static/` 경로를 API 서버 absolute URL로 변환한다.
 * - http(s):// 로 시작하는 URL은 그대로 유지(외부 이미지/이미 변환된 URL).
 * - 그 외 경로는 그대로 반환(public/, data URL 등).
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function resolveAssetUrl(url: string): string {
  if (!url) return url;
  const trimmed = url.trim();
  if (!trimmed) return url;
  if (trimmed.startsWith("http://") || trimmed.startsWith("https://")) {
    return trimmed;
  }
  if (trimmed.startsWith("/static/")) {
    return `${API_BASE}${trimmed}`;
  }
  return url;
}

/**
 * HTML 문자열 안의 `<img src="/static/...">` 들을 API 서버 absolute URL로 변환.
 * 에디터가 본문을 렌더하기 전에 한 번 통과시켜 broken image를 방지한다.
 *
 * - 이미 absolute(http/https)인 src는 건드리지 않는다.
 * - 상대 `/static/...` src만 prefix를 붙인다.
 */
export function toEditorHtml(html: string): string {
  if (!html) return html;
  return html.replace(
    /(<img\b[^>]*\bsrc=")(\/static\/[^"]+)(")/gi,
    (_match, prefix: string, path: string, suffix: string) =>
      `${prefix}${API_BASE}${path}${suffix}`,
  );
}
