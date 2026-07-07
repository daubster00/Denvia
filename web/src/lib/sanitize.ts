"use client";

/** isomorphic-dompurify 클라이언트 sanitize — Story 4.5 AC-13 + 7.2 v3.
 *
 * 서버 nh3 sanitize에 더해 클라이언트에서도 한 번 더 sanitize하여
 * XSS 이중 방어. ALLOWED_URI_REGEXP는 https?:// 만 허용 — mailto:는
 * 의도적으로 차단(이메일 0건 정책 일관, memory project_email_zero_policy).
 *
 * Story 7.2 v3 — <span style="color: ...; font-size: ...">를 허용한다.
 * 단 style 속성 값은 화이트리스트(8 프리셋 색 + 5 크기 px)만 통과시킨다.
 * 서버 sanitize와 동일한 규칙으로 이중 방어.
 */

import DOMPurify from "isomorphic-dompurify";

const ALLOWED_COLORS = new Set<string>([
  "#18181b",
  "#6b7280",
  "#dc2626",
  "#ea580c",
  "#ca8a04",
  "#16a34a",
  "#2563eb",
  "#7c3aed",
]);
const ALLOWED_FONT_SIZES_PX = new Set<number>([12, 14, 16, 20, 24]);
const STYLE_PROP_RX = /\s*([a-z-]+)\s*:\s*([^;]+?)\s*(?:;|$)/g;
const HEX_RX = /^#[0-9a-fA-F]{6}$/;
// rgb(R, G, B) / rgba(R, G, B, 1) — 브라우저 DOM 정규화 형식(공백 유무 무관)
const RGB_RX = /^rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*(?:,\s*(\d*\.?\d+)\s*)?\)$/;
const PX_RX = /^(\d+)px$/;

/** color 값을 소문자 hex(#rrggbb)로 정규화. 인식 불가 형식이면 null.
 *
 * Tiptap으로 기존 글을 다시 열어 편집하면 브라우저 DOM 정규화 때문에
 * 프리셋 hex가 `rgb(220, 38, 38)` 형식으로 바뀐다(수정요청 #119).
 * 이 형식도 hex로 되돌려 프리셋 검사를 통과할 수 있게 한다.
 * alpha가 1이 아닌 rgba는 프리셋 색과 동치가 아니므로 정규화하지 않는다.
 * 서버 api/src/utils/html_sanitize.py의 _normalize_color_to_hex와 동일 규칙.
 */
export function normalizeCssColorToHex(raw: string): string | null {
  if (HEX_RX.test(raw)) return raw.toLowerCase();
  const m = RGB_RX.exec(raw.toLowerCase());
  if (!m) return null;
  const r = parseInt(m[1], 10);
  const g = parseInt(m[2], 10);
  const b = parseInt(m[3], 10);
  if (r > 255 || g > 255 || b > 255) return null;
  if (m[4] !== undefined && parseFloat(m[4]) !== 1) return null;
  return `#${[r, g, b]
    .map((v) => v.toString(16).padStart(2, "0"))
    .join("")}`;
}

function filterSpanStyle(value: string): string | null {
  if (!value) return null;
  const kept: string[] = [];
  let match: RegExpExecArray | null;
  STYLE_PROP_RX.lastIndex = 0;
  while ((match = STYLE_PROP_RX.exec(value)) !== null) {
    const prop = match[1].toLowerCase();
    const raw = match[2].trim();
    if (prop === "color") {
      const hex = normalizeCssColorToHex(raw);
      if (hex !== null && ALLOWED_COLORS.has(hex)) {
        kept.push(`color: ${hex}`);
      }
    } else if (prop === "font-size") {
      const px = PX_RX.exec(raw);
      if (px && ALLOWED_FONT_SIZES_PX.has(parseInt(px[1], 10))) {
        kept.push(`font-size: ${px[1]}px`);
      }
    }
  }
  return kept.length > 0 ? kept.join("; ") : null;
}

const PROFILE_INBOX = {
  ALLOWED_TAGS: [
    "b",
    "strong",
    "i",
    "em",
    "ul",
    "ol",
    "li",
    "a",
    "img",
    "p",
    "br",
    "span",
  ],
  ALLOWED_ATTR: ["href", "src", "alt", "target", "rel", "style"],
  ALLOWED_URI_REGEXP: /^https?:\/\//i,
};

let hookInstalled = false;
function ensureSpanStyleHook() {
  if (hookInstalled) return;
  hookInstalled = true;
  DOMPurify.addHook("uponSanitizeAttribute", (node, data) => {
    if (data.attrName !== "style") return;
    if (node.nodeName?.toLowerCase() !== "span") {
      data.keepAttr = false;
      return;
    }
    const filtered = filterSpanStyle(data.attrValue ?? "");
    if (filtered === null) {
      data.keepAttr = false;
      return;
    }
    data.attrValue = filtered;
    data.keepAttr = true;
  });
}

export function sanitizeNoticeHtml(html: string): string {
  ensureSpanStyleHook();
  return DOMPurify.sanitize(html, PROFILE_INBOX) as unknown as string;
}
