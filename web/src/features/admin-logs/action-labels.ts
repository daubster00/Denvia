/**
 * 활동 로그 액션 코드 → 한글 라벨 매핑.
 *
 * SSOT: `api/src/middleware/audit_actions.py` 의 `AUDIT_*` 상수.
 * 백엔드가 새 액션을 추가하면 본 맵에도 추가. 누락 시 원본 코드를 그대로 노출(fallback).
 */

export const ACTION_LABELS: Record<string, string> = {
  // 사용자 관리
  "user.permission_edit": "사용자 권한 변경",
  "user.block_auto_expired": "사용자 차단 자동 만료",
  "user.speed_override": "응답 속도 단독 변경",
  "user.withdraw": "회원 탈퇴",
  "user.anomaly_throttle_clear": "이상행동 차단 해제",
  "user.login_lockout_clear": "로그인 잠금 해제",

  // 관리자 쪽지 / 공지
  "admin_dm.send": "관리자 쪽지 발송",
  "admin_dm.delete": "관리자 쪽지 회수",
  "notice.publish": "공지 발행",
  "notice.create": "공지 작성",
  "notice.delete": "공지 회수",
  "inbox_preview_config.update": "받은쪽지함 미리보기 설정 변경",

  // 팝업
  "popup.create": "팝업 생성",
  "popup.update": "팝업 수정",
  "popup.toggle": "팝업 활성/비활성",
  "popup.delete": "팝업 삭제",
  "popup.image_upload": "팝업 이미지 업로드",

  // CS · 환불
  "support.reply": "문의 답변",
  "support.reply_edit": "문의 답변 수정",
  "support.reply_delete": "문의 답변 삭제",
  "support.reply_image_upload": "문의 답변 이미지 업로드",
  "refund.manual.approve": "환불 수동 승인",
  "refund.manual.deny": "환불 수동 거부",
  "refund.operational.create": "운영 환불 실행",

  // RAG · 프롬프트
  "rag.upload": "RAG 파일 업로드",
  "rag.knowledge_edit": "RAG 지식 편집",
  "rag.knowledge_delete": "RAG 지식 삭제",
  "rag.rebuild": "RAG 재구축",
  "prompt.edit": "프롬프트 수정",
  "rag.model_params.update": "RAG 모델 파라미터 변경",
  "rag.synonym.edit": "동의어 사전 편집",
  "rag.synonym.export": "동의어 사전 내보내기",

  // 운영 설정
  "killswitch.toggle": "비상정지 토글",
  "killswitch.manual_total.activate": "수동 비상정지 발동",
  "killswitch.manual_total.deactivate": "수동 비상정지 해제",
  "anomaly.review": "이상탐지 검토 처리",
  "anomaly_throttle_config.update": "이상질문 차단 설정 변경",
  "login_brute_threshold.update": "로그인 실패 임계치 변경",
  "runtime_config.update": "런타임 설정 변경",
  "budget.monthly_limit.update": "월 예산 한도 변경",
  "seo_config.update": "SEO 설정 변경",
  "seo_config.asset_upload": "SEO 이미지 업로드",
  "pg_config.update": "결제(PG) 설정 변경",

  // 관리자 계정 (Story 10.3 / 10.5)
  "admin.account.approved": "관리자 승인",
  "admin.account.blocked": "관리자 차단",
  "admin.account.unblocked": "관리자 차단 해제",
  "admin.account.deleted": "관리자 삭제",
  "admin.account.grade_updated": "관리자 등급 변경",
  "admin.master.protection_triggered": "마스터 계정 변경 차단 발동",
  "admin.grade_permission.updated": "관리자 권한 매트릭스 변경",
  "admin.grade.created": "관리자 등급 추가",
  "admin.grade.deleted": "관리자 등급 삭제",
  "admin.auth.pending_login_attempt": "승인대기 관리자 로그인 시도",
};

export function labelForAction(action: string): string {
  return ACTION_LABELS[action] ?? action;
}
