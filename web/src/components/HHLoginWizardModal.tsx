import React, { useState } from "react";
import { CheckCircle2, KeyRound, Loader2, Phone, Shield, X } from "lucide-react";
import { startHHLogin, updateUserSettings, verifyHHCode } from "../api";
import { ResumeOption } from "../types";

interface HHLoginWizardModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
  defaultProxy?: string | null;
}

export const HHLoginWizardModal: React.FC<HHLoginWizardModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
  defaultProxy = "",
}) => {
  const [step, setStep] = useState<"phone" | "code" | "resume">("phone");
  const [phone, setPhone] = useState("");
  const [proxyUrl, setProxyUrl] = useState(defaultProxy || "");
  const [code, setCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resumes, setResumes] = useState<ResumeOption[]>([]);
  const [selectedResumeId, setSelectedResumeId] = useState("");

  if (!isOpen) return null;

  const handleStartLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!phone || phone.trim().length < 10) {
      setError("Введите корректный номер телефона (например, +79991234567)");
      return;
    }

    try {
      setLoading(true);
      await startHHLogin(phone.trim(), proxyUrl.trim() || undefined);
      setStep("code");
    } catch (err: any) {
      setError(err.message || "Ошибка отправки СМС с кодом");
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyCode = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!code || code.trim().length < 4) {
      setError("Введите код подтверждения из СМС");
      return;
    }

    try {
      setLoading(true);
      const res = await verifyHHCode(code.trim());
      const fetchedResumes = res.resumes || [];
      setResumes(fetchedResumes);
      if (fetchedResumes.length > 0) {
        setSelectedResumeId(fetchedResumes[0].id);
        setStep("resume");
      } else {
        onSuccess();
        onClose();
      }
    } catch (err: any) {
      setError(err.message || "Ошибка проверки кода подтверждения");
    } finally {
      setLoading(false);
    }
  };

  const handleSaveResume = async () => {
    try {
      setLoading(true);
      const chosen = resumes.find((r) => r.id === selectedResumeId);
      await updateUserSettings({
        selected_resume_id: selectedResumeId,
        selected_resume_title: chosen ? chosen.title : undefined,
      });
      onSuccess();
      onClose();
    } catch (err: any) {
      setError(err.message || "Не удалось сохранить выбранное резюме");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-fade-in">
      <div className="bg-slate-900 border border-slate-700 w-full max-w-md rounded-2xl p-6 shadow-2xl relative text-slate-100">
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors"
          disabled={loading}
        >
          <X className="w-5 h-5" />
        </button>

        {/* Header */}
        <div className="flex items-center space-x-3 mb-6">
          <div className="p-2.5 bg-blue-600/20 text-blue-400 rounded-xl border border-blue-500/30">
            {step === "phone" && <Phone className="w-6 h-6" />}
            {step === "code" && <KeyRound className="w-6 h-6" />}
            {step === "resume" && <CheckCircle2 className="w-6 h-6 text-emerald-400" />}
          </div>
          <div>
            <h2 className="text-xl font-bold tracking-tight text-white">
              {step === "phone" && "Подключение HeadHunter"}
              {step === "code" && "Подтверждение по СМС"}
              {step === "resume" && "Выбор резюме для откликов"}
            </h2>
            <p className="text-xs text-slate-400">
              {step === "phone" && "Безопасная авторизация через мобильный номер"}
              {step === "code" && `Код отправлен на номер ${phone}`}
              {step === "resume" && "Выберите резюме из вашего профиля hh.ru"}
            </p>
          </div>
        </div>

        {error && (
          <div className="mb-4 p-3 bg-rose-500/10 border border-rose-500/30 rounded-xl text-rose-300 text-xs flex items-center">
            <span>{error}</span>
          </div>
        )}

        {/* STEP 1: Phone & Proxy */}
        {step === "phone" && (
          <form onSubmit={handleStartLogin} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                Номер телефона hh.ru
              </label>
              <div className="relative">
                <input
                  type="tel"
                  placeholder="+79991234567"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  disabled={loading}
                  className="w-full bg-slate-950/80 border border-slate-700 rounded-xl px-4 py-2.5 text-white placeholder-slate-500 text-sm focus:outline-none focus:border-blue-500 font-mono"
                  required
                  autoFocus
                />
              </div>
              <p className="text-[11px] text-slate-400 mt-1">
                Номер, привязанный к вашему аккаунту соискателя на hh.ru
              </p>
            </div>

            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-xs font-semibold text-slate-300 flex items-center">
                  <Shield className="w-3.5 h-3.5 mr-1 text-slate-400" />
                  Прокси (опционально)
                </label>
                <span className="text-[10px] text-slate-400 font-mono">RU HTTP / SOCKS5</span>
              </div>
              <input
                type="text"
                placeholder="http://user:pass@ip:port или socks5://ip:port"
                value={proxyUrl}
                onChange={(e) => setProxyUrl(e.target.value)}
                disabled={loading}
                className="w-full bg-slate-950/80 border border-slate-700 rounded-xl px-4 py-2 text-white placeholder-slate-500 text-xs focus:outline-none focus:border-blue-500 font-mono"
              />
              <p className="text-[11px] text-slate-500 mt-1">
                Для серверов в Европе (Нидерланды) необходим российский прокси, чтобы hh.ru не блокировал соединение.
              </p>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full mt-2 py-3 px-4 bg-blue-600 hover:bg-blue-500 text-white font-semibold text-sm rounded-xl shadow-lg shadow-blue-600/30 transition-all flex items-center justify-center disabled:opacity-50"
            >
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Запуск браузера и отправка СМС...
                </>
              ) : (
                "Получить код по СМС"
              )}
            </button>
          </form>
        )}

        {/* STEP 2: SMS Code */}
        {step === "code" && (
          <form onSubmit={handleVerifyCode} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                Код из СМС
              </label>
              <input
                type="text"
                maxLength={6}
                placeholder="4 или 6 цифр"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                disabled={loading}
                className="w-full text-center tracking-widest text-2xl font-bold bg-slate-950/80 border border-slate-700 rounded-xl py-3 text-white focus:outline-none focus:border-blue-500 font-mono"
                required
                autoFocus
              />
              <p className="text-[11px] text-slate-400 text-center mt-2">
                Введите код, полученный от HeadHunter на номер {phone}
              </p>
            </div>

            <div className="space-y-2 pt-2">
              <button
                type="submit"
                disabled={loading}
                className="w-full py-3 px-4 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-sm rounded-xl shadow-lg shadow-emerald-600/30 transition-all flex items-center justify-center disabled:opacity-50"
              >
                {loading ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    Вход и сохранение сессии...
                  </>
                ) : (
                  "Подтвердить и войти"
                )}
              </button>

              <button
                type="button"
                onClick={() => setStep("phone")}
                disabled={loading}
                className="w-full py-2 px-3 text-xs text-slate-400 hover:text-white transition-colors"
              >
                ← Изменить номер телефона
              </button>
            </div>
          </form>
        )}

        {/* STEP 3: Resume Selection */}
        {step === "resume" && (
          <div className="space-y-4">
            <div className="p-3 bg-emerald-500/10 border border-emerald-500/30 rounded-xl text-emerald-300 text-xs">
              ✓ Аккаунт HeadHunter успешно подключен! Выберите резюме, с которого бот будет откликаться на вакансии:
            </div>

            <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
              {resumes.map((r) => (
                <label
                  key={r.id}
                  className={`flex items-center p-3 rounded-xl border cursor-pointer transition-all ${
                    selectedResumeId === r.id
                      ? "bg-blue-600/20 border-blue-500 text-white"
                      : "bg-slate-950/50 border-slate-800 text-slate-300 hover:border-slate-700"
                  }`}
                >
                  <input
                    type="radio"
                    name="resume"
                    value={r.id}
                    checked={selectedResumeId === r.id}
                    onChange={() => setSelectedResumeId(r.id)}
                    className="mr-3 text-blue-600 focus:ring-0"
                  />
                  <span className="text-sm font-medium">{r.title}</span>
                </label>
              ))}
            </div>

            <button
              onClick={handleSaveResume}
              disabled={loading}
              className="w-full mt-3 py-3 px-4 bg-blue-600 hover:bg-blue-500 text-white font-semibold text-sm rounded-xl shadow-lg shadow-blue-600/30 transition-all flex items-center justify-center disabled:opacity-50"
            >
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Сохранение...
                </>
              ) : (
                "Готово"
              )}
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
