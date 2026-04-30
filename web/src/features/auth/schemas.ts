import { z } from "zod";

/** 로그인 폼 스키마 */
export const loginSchema = z.object({
  email: z.string().email("올바른 이메일을 입력하세요."),
  password: z.string().min(8, "비밀번호는 8자 이상이어야 합니다."),
});

export type LoginFormValues = z.infer<typeof loginSchema>;

/** 회원가입 폼 스키마 */
const phoneRegex = /^010[-\s]?\d{4}[-\s]?\d{4}$/;

export const signupSchema = z.object({
  email: z.string().email("올바른 이메일을 입력하세요."),
  password: z.string().min(8, "비밀번호는 8자 이상이어야 합니다."),
  phone: z.string().regex(phoneRegex, "올바른 휴대폰 번호를 입력하세요. (010-XXXX-XXXX)"),
  phone_verification_token: z.string().min(1, "SMS 인증이 필요합니다."),
  agreed_to_terms: z.boolean().refine((v) => v === true, {
    message: "이용약관에 동의해주세요.",
  }),
  agreed_to_privacy: z.boolean().refine((v) => v === true, {
    message: "개인정보 처리방침에 동의해주세요.",
  }),
});

export type SignupFormValues = z.infer<typeof signupSchema>;

/** 가입유형 스키마 */
export const segmentSchema = z.discriminatedUnion("segment", [
  z.object({
    segment: z.literal("doctor"),
    years_of_experience: z.number().int().min(1).max(50, "연차는 1~50 사이여야 합니다."),
  }),
  z.object({
    segment: z.literal("hygienist"),
    years_of_experience: z.number().int().min(1).max(50, "연차는 1~50 사이여야 합니다."),
  }),
  z.object({
    segment: z.literal("student_other"),
    years_of_experience: z.undefined().optional(),
  }),
]);

export type SegmentFormValues = z.infer<typeof segmentSchema>;

/** 비밀번호 찾기 폼 스키마 */
export const findPasswordSchema = z.object({
  email: z.string().email("올바른 이메일을 입력하세요."),
  phone: z.string().regex(/^010[-\s]?\d{4}[-\s]?\d{4}$/, "올바른 휴대폰 번호를 입력하세요. (010-XXXX-XXXX)"),
});

export type FindPasswordFormValues = z.infer<typeof findPasswordSchema>;

/** 아이디 찾기 — 휴대폰 입력 단계 */
export const findIdPhoneSchema = z.object({
  phone: z.string().regex(/^010[-\s]?\d{4}[-\s]?\d{4}$/, "올바른 휴대폰 번호를 입력하세요. (010-XXXX-XXXX)"),
});

export type FindIdPhoneFormValues = z.infer<typeof findIdPhoneSchema>;

/** 비밀번호 재설정 폼 스키마 */
export const resetPasswordSchema = z
  .object({
    new_password: z.string().min(8, "비밀번호는 8자 이상이어야 합니다."),
    confirm: z.string().min(1, "비밀번호 확인을 입력하세요."),
  })
  .refine((data) => data.new_password === data.confirm, {
    message: "비밀번호가 일치하지 않습니다.",
    path: ["confirm"],
  });

export type ResetPasswordFormValues = z.infer<typeof resetPasswordSchema>;
