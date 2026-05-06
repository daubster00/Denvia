"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  updateUserPermission,
  type UserPermissionUpdatePayload,
  type UserSearchItem,
} from "@/features/admin-users/api/users";

interface MutationVariables {
  userId: number;
  payload: UserPermissionUpdatePayload;
}

/**
 * Story 6.2 — 권한 편집 useMutation 훅.
 *
 * onSuccess 시:
 *  - admin/users 목록 무효화 (Drawer 뒤편 테이블 자동 갱신)
 *  - admin/user/{id} 단건 무효화 (Drawer 자동 갱신)
 *  - admin/audit-logs 무효화 (이력 페이지 진입 시 최신 반영)
 * Toast/에러 인라인 표시는 호출자(Dialog)가 담당.
 */
export function useUpdatePermission() {
  const qc = useQueryClient();
  return useMutation<UserSearchItem, Error, MutationVariables>({
    mutationFn: ({ userId, payload }) => updateUserPermission(userId, payload),
    onSuccess: (_data, { userId }) => {
      qc.invalidateQueries({ queryKey: ["admin", "users"] });
      qc.invalidateQueries({ queryKey: ["admin", "user", userId] });
      qc.invalidateQueries({ queryKey: ["admin", "audit-logs"] });
    },
  });
}
