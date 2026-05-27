/**
 * 활동 로그 diff_json → 비개발자도 읽을 수 있는 한글 설명 라인 변환.
 *
 * 백엔드 audit_diff 구조가 액션마다 제각각이라 (`before/after` 표준 + 특수 모양들),
 * 흔한 모양은 일반 포맷터로 처리하고 특수 모양(killswitch, refund, budget 등)은
 * 액션 코드 단위로 오버라이드한다.
 *
 * 모르는 필드/값은 원본 그대로 노출(폴백). 백엔드가 새 필드를 추가하면
 * `FIELD_LABELS` 와 `VALUE_LABELS` 에 보강하면 끝.
 */

export interface DescriptionLine {
  label: string;
  before?: string;
  after?: string;
  value?: string;
}

const FIELD_LABELS: Record<string, string> = {
  // 사용자 관리
  subscription_status: "구독 상태",
  segment: "사용자 그룹",
  daily_quota_override: "일일 질문 한도(수동)",
  free_delay_override: "응답 지연(수동, 초)",
  is_blocked: "차단 여부",
  blocked_until: "차단 만료 시각",
  anomaly_throttled_at: "이상행동 차단 시각",
  login_lockout_keys: "로그인 잠금 키",
  block_reason: "차단 사유",
  pro_granted_by_admin: "관리자 Pro 부여",
  cleared: "해제 완료",
  target_user_id: "대상 사용자 ID",

  // 쪽지 / 공지
  title: "제목",
  title_length: "제목 글자 수",
  body_length: "본문 글자 수",
  target_segment: "대상 사용자 그룹",
  published_at: "발행 시각",
  delivered_user_count: "발송 대상 수",
  deleted: "삭제 여부",

  // 팝업
  popup_type: "팝업 종류",
  display_position: "표시 위치",
  display_position_top_px: "표시 위치(상단 px)",
  display_position_left_px: "표시 위치(좌측 px)",
  sort_order: "정렬 순서",
  display_start: "노출 시작",
  display_end: "노출 종료",
  is_active: "활성 여부",
  link_url: "링크 URL",
  image_url: "이미지 URL",
  filename: "파일명",
  original_name: "원본 파일명",
  size_bytes: "파일 크기(바이트)",
  mime_type: "파일 형식",
  target_device: "대상 기기",
  deleted_at: "삭제 시각",

  // CS / 환불
  status: "상태",
  resolved_at: "처리 완료 시각",
  reply_id: "답변 ID",
  reply_html_length: "답변 글자 수",
  reply_sent: "답변 발송 여부",
  force: "강제 처리",
  payment_id: "결제 ID",
  cancel_amount: "환불 금액(원)",
  original_payment_amount: "원 결제 금액(원)",
  refunded_total_after: "누적 환불액(원)",
  refund_sequence: "환불 순번",
  reason_category: "환불 사유 분류",
  memo_length: "관리자 메모 글자 수",
  refund_reason: "환불 사유",
  is_fully_refunded: "전액 환불",
  idempotency_key: "멱등성 키",

  // 운영 설정 / 비상정지 / 예산
  reason: "사유",
  duration_seconds: "정지 지속 시간(초)",
  year_month: "적용 연월",
  monthly_limit_usd: "월 예산 한도(USD)",
  show_subscribe_button: "구독 버튼 표시",
  free_daily_quota: "무료 일일 한도",
  free_delay_enabled: "무료 응답 지연 활성",
  free_delay_seconds: "무료 응답 지연 시간(초)",
  free_delay_notice_text: "무료 지연 안내 문구",
  pro_monthly_quota: "Pro 월 한도",

  // SEO
  site_name: "사이트 이름",
  site_description: "사이트 설명",
  keywords: "검색 키워드",
  og_image_url: "OG 이미지 URL",
  favicon_url: "파비콘 URL",
  kind: "자산 종류",
  asset_url: "자산 URL",

  // 관리자 계정 / RBAC
  admin_grade: "관리자 등급",
  admin_blocked_until: "관리자 차단 만료",
  admin_block_reason: "관리자 차단 사유",
  withdrawn_at: "탈퇴 시각",
  allowed: "권한 허용",
  page_route: "페이지 경로",

  // RAG
  pending_changes_count: "대기 중 변경 건수",
  target_slot: "대상 슬롯",
  canceled: "취소됨",
  job_id: "작업 ID",
  op: "작업 종류",

  // 받은쪽지함 미리보기 설정
  inbox_preview_max_count: "받은쪽지함 미리보기 최대 개수",
};

// 필드별 enum 값 → 한글
const VALUE_LABELS: Record<string, Record<string, string>> = {
  subscription_status: {
    active: "활성",
    trialing: "체험중",
    canceled: "취소",
    past_due: "연체",
    paused: "일시정지",
    none: "미가입",
  },
  admin_grade: {
    master: "마스터",
    operator: "운영자",
    sub_operator: "보조 운영자",
    pending: "승인대기",
  },
  target_segment: {
    all: "전체",
    free: "무료",
    pro: "Pro",
    trialing: "체험중",
    none: "미가입",
  },
  segment: {
    all: "전체",
    free: "무료",
    pro: "Pro",
    trialing: "체험중",
    none: "미가입",
  },
  target_device: {
    all: "전체",
    mobile: "모바일",
    desktop: "데스크탑",
    pc: "PC",
  },
  popup_type: {
    image: "이미지",
    html: "HTML",
    text: "텍스트",
  },
  status: {
    open: "열림",
    in_progress: "처리중",
    pending: "대기",
    resolved: "완료",
    closed: "종료",
  },
  reason_category: {
    service_issue: "서비스 장애",
    user_request: "사용자 요청",
    accidental_charge: "오결제",
    duplicate_charge: "중복 결제",
    other: "기타",
  },
  kind: {
    favicon: "파비콘",
    og_image: "OG 이미지",
  },
  op: {
    create: "생성",
    update: "수정",
    delete: "삭제",
    bulk_import: "일괄 가져오기",
  },
};

const ISO_DATE_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/;

function _utcIsoToKstDisplay(iso: string): string {
  const utc = new Date(iso);
  if (Number.isNaN(utc.getTime())) return iso;
  const kstMs = utc.getTime() + 9 * 60 * 60 * 1000;
  const k = new Date(kstMs);
  const yyyy = k.getUTCFullYear();
  const mm = String(k.getUTCMonth() + 1).padStart(2, "0");
  const dd = String(k.getUTCDate()).padStart(2, "0");
  const hh = String(k.getUTCHours()).padStart(2, "0");
  const mi = String(k.getUTCMinutes()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd} ${hh}:${mi}`;
}

function labelForField(field: string): string {
  return FIELD_LABELS[field] ?? field;
}

function formatValue(value: unknown, field?: string): string {
  if (value === null || value === undefined) return "(없음)";
  if (value === "***REDACTED***") return "(마스킹됨)";
  if (typeof value === "boolean") return value ? "예" : "아니오";
  if (typeof value === "number") {
    // 큰 정수는 천 단위 콤마
    if (Number.isInteger(value) && Math.abs(value) >= 1000) {
      return value.toLocaleString("ko-KR");
    }
    return String(value);
  }
  if (typeof value === "string") {
    if (value === "") return "(빈 값)";
    // 필드별 enum 매핑
    if (field && VALUE_LABELS[field]?.[value]) {
      return VALUE_LABELS[field][value];
    }
    // ISO 8601 날짜 자동 KST 변환
    if (ISO_DATE_RE.test(value)) {
      return _utcIsoToKstDisplay(value);
    }
    // 너무 긴 문자열은 잘라 보여줌
    if (value.length > 120) {
      return `${value.slice(0, 120)}…`;
    }
    return value;
  }
  // 객체/배열은 JSON 그대로 (드물게 등장)
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function isObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

/**
 * 표준 before/after 모양에서 변경된 키만 골라 라인으로 변환.
 * - before 만 있고 after 없으면 "삭제" / 반대면 "신규"
 * - 같은 키가 양쪽에 있고 값이 다르면 "이전 → 이후"
 */
function _formatBeforeAfter(
  before: Record<string, unknown> | undefined,
  after: Record<string, unknown> | undefined,
): DescriptionLine[] {
  const lines: DescriptionLine[] = [];
  const keys = new Set<string>([
    ...Object.keys(before ?? {}),
    ...Object.keys(after ?? {}),
  ]);
  for (const key of keys) {
    const b = before?.[key];
    const a = after?.[key];
    const bHas = before !== undefined && key in before;
    const aHas = after !== undefined && key in after;
    if (bHas && aHas) {
      // 값이 같으면 건너뛰기(노이즈 제거)
      if (JSON.stringify(b) === JSON.stringify(a)) continue;
      lines.push({
        label: labelForField(key),
        before: formatValue(b, key),
        after: formatValue(a, key),
      });
    } else if (aHas) {
      lines.push({ label: labelForField(key), value: formatValue(a, key) });
    } else if (bHas) {
      lines.push({
        label: labelForField(key),
        before: formatValue(b, key),
        after: "(제거됨)",
      });
    }
  }
  return lines;
}

/**
 * 특수 모양 처리. 매칭되면 라인 배열을, 아니면 null 을 반환.
 * (예: budget 의 `{year_month, monthly_limit_usd: {before, after}}` 같은 비표준 모양)
 */
function _formatActionSpecific(
  action: string,
  diff: Record<string, unknown>,
): DescriptionLine[] | null {
  // 월 예산 한도 변경 — {year_month, monthly_limit_usd: {before, after}}
  if (action === "budget.monthly_limit.update") {
    const lines: DescriptionLine[] = [];
    if (typeof diff.year_month === "string") {
      lines.push({ label: "적용 연월", value: diff.year_month });
    }
    const m = diff.monthly_limit_usd;
    if (isObject(m)) {
      lines.push({
        label: "월 예산 한도(USD)",
        before: formatValue(m.before),
        after: formatValue(m.after),
      });
    }
    return lines;
  }

  // 수동 비상정지 발동 — {reason}
  if (action === "killswitch.manual_total.activate") {
    return [
      {
        label: "정지 사유",
        value: formatValue(diff.reason),
      },
    ];
  }

  // 수동 비상정지 해제 — {duration_seconds}
  if (action === "killswitch.manual_total.deactivate") {
    const secs = typeof diff.duration_seconds === "number" ? diff.duration_seconds : null;
    return [
      {
        label: "정지 지속 시간",
        value: secs !== null ? _formatDuration(secs) : formatValue(diff.duration_seconds),
      },
    ];
  }

  // 관리자 쪽지 발송 — {target_user_id, title_length, body_length}
  if (action === "admin_dm.send") {
    return [
      { label: "받는 사용자 ID", value: formatValue(diff.target_user_id) },
      { label: "제목 글자 수", value: formatValue(diff.title_length) },
      { label: "본문 글자 수", value: formatValue(diff.body_length) },
    ];
  }

  // CS 답변 등록 — {status_change: {before, after}, reply_id, reply_html_length}
  if (
    action === "support.reply" &&
    isObject(diff.status_change)
  ) {
    const sc = diff.status_change;
    const lines: DescriptionLine[] = [
      {
        label: "상태",
        before: formatValue(sc.before, "status"),
        after: formatValue(sc.after, "status"),
      },
    ];
    if (diff.reply_id !== undefined) {
      lines.push({ label: "답변 ID", value: formatValue(diff.reply_id) });
    }
    if (diff.reply_html_length !== undefined) {
      lines.push({
        label: "답변 글자 수",
        value: formatValue(diff.reply_html_length),
      });
    }
    return lines;
  }

  // 운영 환불 실행 — 여러 필드 평탄
  if (action === "refund.operational.create") {
    const order: Array<[string, string]> = [
      ["payment_id", "결제 ID"],
      ["cancel_amount", "환불 금액(원)"],
      ["original_payment_amount", "원 결제 금액(원)"],
      ["refunded_total_after", "누적 환불액(원)"],
      ["refund_sequence", "환불 순번"],
      ["reason_category", "환불 사유 분류"],
      ["refund_reason", "환불 사유"],
      ["memo_length", "관리자 메모 글자 수"],
      ["is_fully_refunded", "전액 환불 여부"],
    ];
    return order
      .filter(([k]) => k in diff)
      .map(([k, label]) => ({
        label,
        value: formatValue(diff[k], k),
      }));
  }

  // RAG 재구축 — {pending_changes_count, target_slot}
  if (action === "rag.rebuild" && !("before" in diff) && !("after" in diff)) {
    if ("canceled" in diff) {
      return [
        { label: "재구축 취소", value: formatValue(diff.canceled) },
        ...("job_id" in diff
          ? [{ label: "작업 ID", value: formatValue(diff.job_id) }]
          : []),
      ];
    }
    return [
      {
        label: "대기 중 변경 건수",
        value: formatValue(diff.pending_changes_count),
      },
      { label: "대상 슬롯", value: formatValue(diff.target_slot) },
    ];
  }

  // 동의어 삭제 — {op: "delete", before: {...}}
  if (action === "rag.synonym.edit" && diff.op === "delete" && isObject(diff.before)) {
    return [
      { label: "작업 종류", value: "삭제" },
      ..._formatBeforeAfter(diff.before, undefined),
    ];
  }

  // 팝업 이미지 업로드 — {after: {filename, ...}}
  // → 표준 처리로 떨어지지만 'after' 만 있어도 자연스럽게 흐름.

  return null;
}

function _formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}초`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  if (m < 60) return s === 0 ? `${m}분` : `${m}분 ${s}초`;
  const h = Math.floor(m / 60);
  const mm = m % 60;
  if (h < 24) return mm === 0 ? `${h}시간` : `${h}시간 ${mm}분`;
  const d = Math.floor(h / 24);
  const hh = h % 24;
  return hh === 0 ? `${d}일` : `${d}일 ${hh}시간`;
}

/**
 * 메인 진입점. diff_json 을 받아 한글 설명 라인 배열을 반환한다.
 *
 * 처리 우선순위:
 * 1) 액션별 특수 모양 (`_formatActionSpecific`)
 * 2) 표준 before/after 모양
 * 3) metadata 필드가 있으면 별도 라인으로 추가
 * 4) 위 어디에도 안 잡히면 평탄 key/value 로 표시
 *
 * 어떤 라인도 만들 수 없으면 빈 배열을 반환(호출 측에서 폴백 처리).
 */
export function formatDiff(action: string, diff: unknown): DescriptionLine[] {
  if (diff === null || diff === undefined) return [];

  // 백엔드 일부 경로(admin_support_service, admin_payment_service)는
  // JSON 문자열로 저장 — get_log_diff 가 그대로 돌려주면 문자열일 수 있음.
  let parsed: unknown = diff;
  if (typeof parsed === "string") {
    const raw = parsed;
    try {
      parsed = JSON.parse(raw);
    } catch {
      return [{ label: "원본", value: raw }];
    }
  }

  if (!isObject(parsed)) {
    return [{ label: "값", value: formatValue(parsed) }];
  }

  // 1) 액션별 특수 모양
  const special = _formatActionSpecific(action, parsed);
  if (special && special.length > 0) {
    return special;
  }

  const lines: DescriptionLine[] = [];

  // 2) 표준 before/after
  const before = isObject(parsed.before) ? parsed.before : undefined;
  const after = isObject(parsed.after) ? parsed.after : undefined;
  if (before || after) {
    lines.push(..._formatBeforeAfter(before, after));
  }

  // 3) metadata 별도 라인
  if (isObject(parsed.metadata)) {
    for (const [k, v] of Object.entries(parsed.metadata)) {
      lines.push({ label: labelForField(k), value: formatValue(v, k) });
    }
  }

  // 4) before/after/metadata 외의 평탄 필드 (예: reply_sent, force, cleared)
  const handled = new Set(["before", "after", "metadata"]);
  for (const [k, v] of Object.entries(parsed)) {
    if (handled.has(k)) continue;
    // 위에서 special 이 안 잡힌 케이스에서, 평탄 필드도 사람이 읽게 노출
    lines.push({ label: labelForField(k), value: formatValue(v, k) });
  }

  return lines;
}
