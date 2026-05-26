"use client";

import { useCallback, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { signupSchema, type SignupFormValues } from "./schemas";
import { sendSmsOtp, verifySmsOtp, signup } from "./api";
import { PhoneNumberField } from "./PhoneNumberField";
import { SMSCodeInput } from "./SMSCodeInput";
import { AddressLookupField } from "@/features/profile/AddressLookupField";
import { useSessionStore } from "@/stores/session-store";
import { ApiError } from "@/types/api";
import styles from "@/styles/auth-forms.module.css";

type Step = "form" | "sms";

const ERROR_COPY: Record<string, string> = {
  ACCOUNT_EMAIL_DUPLICATE: "이미 존재하는 정보입니다. 로그인해주세요.",
  ACCOUNT_PHONE_DUPLICATE: "이미 존재하는 정보입니다. 로그인해주세요.",
  SMS_TOKEN_INVALID: "휴대폰 인증이 필요합니다.",
  SMS_COOLDOWN_ACTIVE: "잠시 후 다시 요청해주세요.",
  SMS_MAX_RETRIES_EXCEEDED: "인증번호 발송 한도를 초과했습니다. 1시간 후 다시 시도해주세요.",
  SMS_ANOMALY_BLOCKED:
    "비정상적인 인증 시도가 감지되어 24시간 동안 휴대폰 인증이 제한됩니다. 자동화된 접근으로 의심되는 경우 차단되며, 본인이 맞다면 잠시 후 다시 시도해 주세요.",
  SMS_CODE_INVALID: "인증번호가 일치하지 않습니다.",
  SMS_MAX_WRONG_ATTEMPTS: "인증 시도 횟수를 초과했습니다. 인증번호를 다시 요청해주세요.",
};

function normalizePhone(phone: string): string {
  return phone.replace(/\D/g, "");
}

function emptyToNull(v: string | undefined | null): string | null {
  if (v == null) return null;
  const trimmed = v.trim();
  return trimmed.length === 0 ? null : trimmed;
}

/**
 * 이메일 회원가입 폼.
 *
 * 필수: 이메일·비밀번호·비밀번호 확인·휴대폰(SMS 인증)·약관 동의.
 * 선택: 이름·생년월일·성별·주소(다음 우편번호).
 */
export function SignupForm() {
  const router = useRouter();
  const setUser = useSessionStore((s) => s.setUser);
  const closePopup = useSessionStore((s) => s.closePopup);

  const [step, setStep] = useState<Step>("form");
  const [phoneValue, setPhoneValue] = useState("");
  const [smsError, setSmsError] = useState<string | undefined>();
  const [phoneVerificationToken, setPhoneVerificationToken] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [smsRequested, setSmsRequested] = useState(false);
  const [debugSmsCode, setDebugSmsCode] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    setValue,
    setError,
    clearErrors,
    watch,
    formState: { errors },
  } = useForm<SignupFormValues>({
    resolver: zodResolver(signupSchema),
    mode: "onBlur",
    defaultValues: {
      email: "",
      password: "",
      password_confirm: "",
      phone: "",
      phone_verification_token: "",
      name: "",
      birthdate: "",
      gender: "",
      postcode: "",
      address_road: "",
      address_detail: "",
      agreed_to_terms: false,
      agreed_to_privacy: false,
    },
  });

  // 약관 동의 상태 — 가입 버튼 활성화 조건에 사용
  const agreedToTerms = watch("agreed_to_terms");
  const agreedToPrivacy = watch("agreed_to_privacy");

  // 주소·성별은 setValue로 갱신하기 위해 watch로 현재 값을 읽는다 (controlled).
  const genderValue = watch("gender");
  const postcodeValue = watch("postcode") ?? "";
  const addressRoadValue = watch("address_road") ?? "";
  const addressDetailValue = watch("address_detail") ?? "";

  // SMS 발송
  const requestSms = useCallback(async () => {
    const raw = phoneValue;
    if (!/^010[-\s]?\d{4}[-\s]?\d{4}$/.test(raw)) {
      setError("phone", { message: "올바른 휴대폰 번호를 입력하세요." });
      return;
    }
    try {
      const res = await sendSmsOtp(normalizePhone(raw), "signup");
      setDebugSmsCode(res.debug_code ?? null);
      setSmsRequested(true);
      setStep("sms");
      setSmsError(undefined);
    } catch (e) {
      if (e instanceof ApiError) {
        setSmsError(ERROR_COPY[e.code] ?? e.message);
      }
    }
  }, [phoneValue, setError]);

  // OTP 완성 → 검증
  const handleOtpComplete = useCallback(
    async (code: string) => {
      setSmsError(undefined);
      try {
        const res = await verifySmsOtp(normalizePhone(phoneValue), code, "signup");
        setPhoneVerificationToken(res.phone_verification_token);
        setValue("phone_verification_token", res.phone_verification_token, { shouldValidate: true });
      } catch (e) {
        if (e instanceof ApiError) {
          setSmsError(ERROR_COPY[e.code] ?? e.message);
        }
      }
    },
    [phoneValue, setValue]
  );

  // 최종 가입 submit
  const onSubmit = async (data: SignupFormValues) => {
    if (!phoneVerificationToken) {
      setSmsError("SMS 인증이 필요합니다.");
      return;
    }
    setSubmitting(true);
    try {
      const user = await signup({
        email: data.email,
        password: data.password,
        phone: normalizePhone(data.phone),
        phone_verification_token: phoneVerificationToken,
        name: emptyToNull(data.name),
        birthdate: emptyToNull(data.birthdate),
        gender: data.gender === "" ? null : data.gender ?? null,
        postcode: emptyToNull(data.postcode),
        address_road: emptyToNull(data.address_road),
        address_detail: emptyToNull(data.address_detail),
      });
      setUser(user);
      closePopup();
      router.push("/signup/segment");
    } catch (e) {
      if (e instanceof ApiError) {
        const msg = ERROR_COPY[e.code] ?? e.message;
        if (e.code === "ACCOUNT_EMAIL_DUPLICATE") {
          setError("email", { message: msg });
        } else if (e.code === "ACCOUNT_PHONE_DUPLICATE") {
          setError("phone", { message: msg });
        } else {
          setSmsError(msg);
        }
      }
    } finally {
      setSubmitting(false);
    }
  };

  const inputClass = (hasError: boolean) =>
    `${styles.input} ${hasError ? styles.inputError : ""}`;

  const submitDisabled =
    submitting || !phoneVerificationToken || !agreedToTerms || !agreedToPrivacy;

  const todayIso = new Date().toISOString().slice(0, 10);

  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate className={styles.formColumn}>
      {/* 이메일 */}
      <div>
        <label htmlFor="signup-email" className={styles.fieldLabel}>
          이메일 <span aria-label="필수" className={styles.required}>*</span>
        </label>
        <input
          id="signup-email"
          type="email"
          autoComplete="email"
          aria-invalid={!!errors.email}
          aria-describedby={errors.email ? "signup-email-error" : undefined}
          className={inputClass(!!errors.email)}
          {...register("email")}
        />
        {errors.email && (
          <p id="signup-email-error" role="alert" className={styles.fieldError}>
            {errors.email.message}
          </p>
        )}
      </div>

      {/* 휴대폰 번호 — 이메일 다음으로 올려, SMS 인증 단계 흐름이 자연스럽게 이어지도록. */}
      <div>
        <PhoneNumberField
          id="signup-phone"
          value={phoneValue}
          onChange={(v) => {
            setPhoneValue(v);
            setValue("phone", v, { shouldValidate: false });
            // 에러가 이미 표시된 상태에서 올바른 형식으로 수정되면 즉시 에러 해제
            if (errors.phone && /^010[-\s]?\d{4}[-\s]?\d{4}$/.test(v)) {
              clearErrors("phone");
            }
          }}
          error={errors.phone?.message}
        />
        {/* SMS 전송 버튼 */}
        {!smsRequested && (
          <button
            type="button"
            onClick={requestSms}
            className={styles.smsRequestBtn}
          >
            인증번호 전송
          </button>
        )}
      </div>

      {/* SMS OTP 입력 */}
      {step === "sms" && (
        <div>
          <p className={styles.smsHelp}>
            휴대폰으로 전송된 6자리 인증번호를 입력하세요.
          </p>
          {debugSmsCode && (
            <p className={styles.smsHelp}>인증번호: {debugSmsCode}</p>
          )}
          <SMSCodeInput
            onComplete={handleOtpComplete}
            onResend={requestSms}
            error={smsError}
            disabled={!!phoneVerificationToken}
          />
          {phoneVerificationToken && (
            <p className={styles.smsVerified}>
              ✓ 인증이 완료되었습니다.
            </p>
          )}
        </div>
      )}

      {/* 전송 요청 전 에러 */}
      {smsError && step === "form" && (
        <p role="alert" className={styles.inlineErrorText}>{smsError}</p>
      )}

      {/* 비밀번호 */}
      <div>
        <label htmlFor="signup-password" className={styles.fieldLabel}>
          비밀번호 <span aria-label="필수" className={styles.required}>*</span>
        </label>
        <input
          id="signup-password"
          type="password"
          autoComplete="new-password"
          aria-invalid={!!errors.password}
          aria-describedby={errors.password ? "signup-password-error" : undefined}
          className={inputClass(!!errors.password)}
          {...register("password")}
        />
        {errors.password && (
          <p id="signup-password-error" role="alert" className={styles.fieldError}>
            {errors.password.message}
          </p>
        )}
      </div>

      {/* 비밀번호 확인 */}
      <div>
        <label htmlFor="signup-password-confirm" className={styles.fieldLabel}>
          비밀번호 확인 <span aria-label="필수" className={styles.required}>*</span>
        </label>
        <input
          id="signup-password-confirm"
          type="password"
          autoComplete="new-password"
          aria-invalid={!!errors.password_confirm}
          aria-describedby={errors.password_confirm ? "signup-password-confirm-error" : undefined}
          className={inputClass(!!errors.password_confirm)}
          {...register("password_confirm")}
        />
        {errors.password_confirm && (
          <p id="signup-password-confirm-error" role="alert" className={styles.fieldError}>
            {errors.password_confirm.message}
          </p>
        )}
      </div>

      {/* 선택 입력 — 비워둬도 가입됨 */}
      <div className={styles.optionalSection}>
        <p className={styles.optionalSectionTitle}>추가 정보 (선택)</p>
        <p className={styles.optionalSectionHint}>
          비워두셔도 가입할 수 있습니다. 나중에 마이페이지에서 수정할 수 있어요.
        </p>

        {/* 이름 */}
        <div>
          <label htmlFor="signup-name" className={styles.fieldLabel}>이름</label>
          <input
            id="signup-name"
            type="text"
            autoComplete="name"
            maxLength={50}
            aria-invalid={!!errors.name}
            className={inputClass(!!errors.name)}
            {...register("name")}
          />
          {errors.name && (
            <p role="alert" className={styles.fieldError}>{errors.name.message}</p>
          )}
        </div>

        {/* 생년월일 */}
        <div>
          <label htmlFor="signup-birthdate" className={styles.fieldLabel}>생년월일</label>
          <input
            id="signup-birthdate"
            type="date"
            min="1900-01-01"
            max={todayIso}
            aria-invalid={!!errors.birthdate}
            className={inputClass(!!errors.birthdate)}
            {...register("birthdate")}
          />
          {errors.birthdate && (
            <p role="alert" className={styles.fieldError}>{errors.birthdate.message}</p>
          )}
        </div>

        {/* 성별 */}
        <div>
          <span className={styles.fieldLabel}>성별</span>
          <div className={styles.genderRow} role="radiogroup" aria-label="성별">
            <label className={styles.genderOption}>
              <input
                type="radio"
                className={styles.genderRadio}
                value="male"
                checked={genderValue === "male"}
                onChange={() => setValue("gender", "male", { shouldValidate: false })}
              />
              <span>남</span>
            </label>
            <label className={styles.genderOption}>
              <input
                type="radio"
                className={styles.genderRadio}
                value="female"
                checked={genderValue === "female"}
                onChange={() => setValue("gender", "female", { shouldValidate: false })}
              />
              <span>여</span>
            </label>
            {genderValue !== "" && genderValue != null && (
              <button
                type="button"
                className={styles.genderClearBtn}
                onClick={() => setValue("gender", "", { shouldValidate: false })}
              >
                선택 해제
              </button>
            )}
          </div>
        </div>

        {/* 주소 — 다음 우편번호 검색 */}
        <AddressLookupField
          idPrefix="signup"
          value={{
            postcode: postcodeValue,
            address_road: addressRoadValue,
            address_detail: addressDetailValue,
          }}
          onChange={(next) => {
            setValue("postcode", next.postcode, { shouldValidate: false });
            setValue("address_road", next.address_road, { shouldValidate: false });
            setValue("address_detail", next.address_detail, { shouldValidate: false });
          }}
        />
        {errors.postcode && (
          <p role="alert" className={styles.fieldError}>{errors.postcode.message}</p>
        )}
      </div>

      {/* 약관 동의 — 회원가입 시 필수 */}
      <div className={styles.consentBlock}>
        <label className={styles.consentRow}>
          <input
            type="checkbox"
            className={styles.consentCheckbox}
            aria-invalid={!!errors.agreed_to_terms}
            {...register("agreed_to_terms")}
          />
          <span className={styles.consentText}>
            <Link href="/legal/terms" target="_blank" rel="noopener noreferrer" className={styles.consentLink}>
              이용약관
            </Link>
            에 동의합니다
            <span aria-label="필수" className={styles.required}> *</span>
          </span>
        </label>
        {errors.agreed_to_terms && (
          <p role="alert" className={styles.fieldError}>{errors.agreed_to_terms.message}</p>
        )}

        <label className={styles.consentRow}>
          <input
            type="checkbox"
            className={styles.consentCheckbox}
            aria-invalid={!!errors.agreed_to_privacy}
            {...register("agreed_to_privacy")}
          />
          <span className={styles.consentText}>
            <Link href="/legal/privacy" target="_blank" rel="noopener noreferrer" className={styles.consentLink}>
              개인정보 처리방침
            </Link>
            에 동의합니다
            <span aria-label="필수" className={styles.required}> *</span>
          </span>
        </label>
        {errors.agreed_to_privacy && (
          <p role="alert" className={styles.fieldError}>{errors.agreed_to_privacy.message}</p>
        )}
      </div>

      {/* 가입 완료 버튼 */}
      <button
        type="submit"
        disabled={submitDisabled}
        className={`${styles.primaryBtn} ${submitDisabled ? styles.primaryBtnDisabled : ""}`}
      >
        {submitting ? "처리 중..." : "회원가입"}
      </button>
    </form>
  );
}
