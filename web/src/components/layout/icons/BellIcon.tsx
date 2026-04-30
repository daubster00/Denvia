/** BellIcon — Story 4.3 쪽지함 진입 버튼용 인라인 SVG. 외부 의존성 미추가. */

interface BellIconProps {
  size?: number;
  "aria-hidden"?: boolean | "true" | "false";
}

export function BellIcon({ size = 20, ...rest }: BellIconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      {...rest}
    >
      <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
      <path d="M13.73 21a2 2 0 0 1-3.46 0" />
    </svg>
  );
}
