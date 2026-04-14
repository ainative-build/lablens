import type { Language } from "@/lib/i18n";

const CONSENT_TEXT: Record<Language, string> = {
  en: "Your lab data (personal identifiers removed) will be processed by Alibaba DashScope AI to generate explanations. By uploading, you consent to this processing.",
  fr: "Vos données de laboratoire (identifiants personnels supprimés) seront traitées par Alibaba DashScope IA pour générer des explications. En téléchargeant, vous consentez à ce traitement.",
  ar: "سيتم معالجة بيانات مختبرك (مع إزالة المعرفات الشخصية) بواسطة Alibaba DashScope AI لإنشاء التفسيرات. بالتحميل، فأنت توافق على هذه المعالجة.",
  vn: "Dữ liệu xét nghiệm của bạn (đã xóa thông tin cá nhân) sẽ được xử lý bởi Alibaba DashScope AI để tạo giải thích. Bằng cách tải lên, bạn đồng ý với việc xử lý này.",
};

const MEDICAL_DISCLAIMER: Record<Language, string> = {
  en: "This information is for educational purposes only and does not replace professional medical advice. Please consult your healthcare provider.",
  fr: "Ces informations sont fournies à titre éducatif uniquement et ne remplacent pas un avis médical professionnel.",
  ar: "هذه المعلومات لأغراض تعليمية فقط ولا تحل محل المشورة الطبية المهنية.",
  vn: "Thông tin này chỉ mang tính chất giáo dục và không thay thế lời khuyên y tế chuyên nghiệp.",
};

interface Props {
  type: "upload" | "results";
  language?: Language;
}

export function DisclaimerBanner({ type, language = "en" }: Props) {
  const lang = language in CONSENT_TEXT ? language : "en";
  return (
    <div className="rounded-md bg-amber-50 border border-amber-200 p-3 text-sm text-amber-800">
      {type === "upload" && <p className="mb-1">{CONSENT_TEXT[lang]}</p>}
      <p>{MEDICAL_DISCLAIMER[lang]}</p>
    </div>
  );
}
