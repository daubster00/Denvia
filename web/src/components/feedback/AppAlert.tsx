"use client";

import {
  Alert,
  AlertActionArea,
  AlertContainer,
  AlertContent,
  AlertDescription,
  AlertHeading,
  Button,
} from "@wanteddev/wds";
import {
  IconCircleExclamationFill,
  IconCircleInfoFill,
} from "@wanteddev/wds-icon";

import { useAlertStore } from "@/stores/alert-store";
import styles from "./AppAlert.module.css";

/**
 * 전역 단일 AppAlert — `useAlertStore.show(...)`로 어디서든 트리거.
 *
 * Providers에 마운트되어 store.current를 구독한다. level에 따라 아이콘 + 색상 분기.
 * 사용자가 "확인" 또는 커스텀 액션 버튼을 눌러야 닫힘 (자동 dismiss 없음).
 *
 * Snackbar/toast를 대체하는 blocking 패턴 — 계정 충돌처럼 사용자 행동이 필요한 에러에 적합.
 */
export function AppAlert() {
  const current = useAlertStore((s) => s.current);
  const close = useAlertStore((s) => s.close);

  const handleOpenChange = (next: boolean) => {
    if (!next) close();
  };

  // current가 없으면 DOM에 아무것도 남기지 않음 (dimmer 잔재 방지)
  if (!current) return null;

  const { level, title, description, actions } = current;
  const Icon = level === "info" ? IconCircleInfoFill : IconCircleExclamationFill;
  // WDS 아이콘은 currentColor를 사용 → 부모 span의 클래스로 전달
  const iconLevelClass =
    level === "error"
      ? styles.iconWrapError
      : level === "warning"
        ? styles.iconWrapWarning
        : styles.iconWrapInfo;

  const resolvedActions: NonNullable<typeof actions> =
    actions && actions.length > 0
      ? actions
      : [{ label: "확인", variant: "normal" }];

  return (
    <Alert open={true} onOpenChange={handleOpenChange}>
      <AlertContainer>
        <AlertContent>
          <span className={`${styles.iconWrap} ${iconLevelClass}`}>
            <Icon width="1em" height="1em" />
          </span>
          <AlertHeading align="center">{title}</AlertHeading>
          {description && (
            <AlertDescription align="center">
              {description.split("\n").map((line, i, arr) => (
                <span key={i}>
                  {line}
                  {i < arr.length - 1 && <br />}
                </span>
              ))}
            </AlertDescription>
          )}
        </AlertContent>
        <AlertActionArea sx={{ justifyContent: "center", gap: "8px" }}>
          {resolvedActions.map((action, i) => (
            <Button
              key={`${action.label}-${i}`}
              variant={action.variant === "assistive" ? "outlined" : "solid"}
              color={action.variant === "assistive" ? "assistive" : "primary"}
              size="medium"
              onClick={() => {
                action.onClick?.();
                close();
              }}
            >
              {action.label}
            </Button>
          ))}
        </AlertActionArea>
      </AlertContainer>
    </Alert>
  );
}
