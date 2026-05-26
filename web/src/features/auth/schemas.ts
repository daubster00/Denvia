import { z } from "zod";

/** 로그인 폼 스키마 */
export const loginSchema = z.object({
  email: z.string().email("올바른 이메일을 입력하세요."),
  password: z.string().min(8, "비밀번호는 8자 이상이어야 합니다."),
});

export type LoginFormValues = z.infer<typeof loginSchema>;

/** 회원가입 폼 스키마 */
const phoneRegex = /^010[-\s]?\d{4}[-\s]?\d{4}$/;
const postcodeRegex = /^\d{5,10}$/;

export const signupSchema = z
  .object({
    email: z.string().email("올바른 이메일을 입력하세요."),
    password: z.string().min(8, "비밀번호는 8자 이상이어야 합니다."),
    password_confirm: z.string().min(1, "비밀번호 확인을 입력하세요."),
    phone: z.string().regex(phoneRegex, "올바른 휴대폰 번호를 입력하세요. (010-XXXX-XXXX)"),
    phone_verification_token: z.string().min(1, "SMS 인증이 필요합니다."),
    // 선택 입력 — 빈 문자열 허용. 백엔드에서 빈값은 NULL로 정규화.
    // useForm.defaultValues에서 ""로 초기화하므로 zod default는 불필요(input/output 타입
    // 불일치를 피하기 위해 default 미사용).
    name: z.string().max(50, "이름은 50자 이내로 입력하세요."),
    birthdate: z
      .string()
      .refine(
        (v) => {
          if (!v) return true;
          if (!/^\d{4}-\d{2}-\d{2}$/.test(v)) return false;
          const d = new Date(v);
          if (Number.isNaN(d.getTime())) return false;
          const year = d.getUTCFullYear();
          const today = new Date();
          return year >= 1900 && d.getTime() <= today.getTime();
        },
        { message: "생년월일이 올바르지 않습니다." }
      ),
    gender: z.enum(["male", "female", ""]),
    postcode: z.string().refine((v) => !v || postcodeRegex.test(v), {
      message: "우편번호 형식이 올바르지 않습니다.",
    }),
    address_road: z.string().max(255),
    address_detail: z.string().max(100),
    agreed_to_terms: z.boolean().refine((v) => v === true, {
      message: "이용약관에 동의해주세요.",
    }),
    agreed_to_privacy: z.boolean().refine((v) => v === true, {
      message: "개인정보 처리방침에 동의해주세요.",
    }),
  })
  .refine((data) => data.password === data.password_confirm, {
    message: "비밀번호가 일치하지 않습니다.",
    path: ["password_confirm"],
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
