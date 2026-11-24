import React, { useEffect, useState } from "react";
import {
  Check,
  Globe,
  Key,
  RotateCcw,
  Save,
  Search,
  Shield,
  ShieldAlert,
} from "lucide-react";
import {
  fetchCurrentUser,
  fetchSettings,
  resetUserVacancies,
  updateSettings,
  updateUserSettings,
} from "../api";
import { SettingsData, UserProfile } from "../types";

interface SettingsProps {
  currentUser?: UserProfile | null;
  onOpenHHLogin?: () => void;
  onUserUpdated?: () => void;
}

export const Settings: React.FC<SettingsProps> = ({
  currentUser: initialUser,
  onOpenHHLogin,
  onUserUpdated,
}) => {
  const [formData, setFormData] = useState<Partial<SettingsData>>({});
  const [userProfile, setUserProfile] = useState<UserProfile | null>(initialUser || null);
  const [userSettingsForm, setUserSettingsForm] = useState({
    search_query: initialUser?.search_query || "DevOps",
    search_region: initialUser?.search_region || 1,
    target_salary: initialUser?.target_salary || "180000",
    proxy_url: initialUser?.proxy_url || "",
    gigachat_auth_key: "",
    gigachat_scope: "GIGACHAT_API_PERS",
  });

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savedSuccess, setSavedSuccess] = useState(false);
  const [resettingVacancies, setResettingVacancies] = useState(false);
  const [resetMessage, setResetMessage] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        const [settingsData, userData] = await Promise.all([
          fetchSettings().catch(() => ({} as SettingsData)),
          fetchCurrentUser().catch(() => null),
        ]);
        setFormData(settingsData);
        if (userData) {
          setUserProfile(userData);
          setUserSettingsForm({
            search_query: userData.search_query || "DevOps",
            search_region: userData.search_region || 1,
            target_salary: userData.target_salary || "180000",
            proxy_url: userData.proxy_url || "",
            gigachat_auth_key: "",
            gigachat_scope: "GIGACHAT_API_PERS",
          });
        }
      } catch (err) {
        console.error("Failed to load settings:", err);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const handleUserSettingsChange = (field: string, value: any) => {
    setUserSettingsForm((prev) => ({ ...prev, [field]: value }));
  };

  const handleGlobalChange = (
    field: keyof SettingsData,
    value: string | number | null
  ) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
  };

  const handleSaveAll = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setSaving(true);
      // 1. Update personal user settings
      const payload: any = {
        search_query: userSettingsForm.search_query,
        search_region: Number(userSettingsForm.search_region) || 1,
        target_salary: userSettingsForm.target_salary,
        proxy_url: userSettingsForm.proxy_url || null,
        gigachat_scope: userSettingsForm.gigachat_scope,
      };
      if (userSettingsForm.gigachat_auth_key.trim()) {
        payload.gigachat_auth_key = userSettingsForm.gigachat_auth_key.trim();
      }
      await updateUserSettings(payload);

      // 2. Update general system settings
      await updateSettings(formData).catch(() => {});

      if (onUserUpdated) onUserUpdated();
      setSavedSuccess(true);
      setTimeout(() => setSavedSuccess(false), 3000);
    } catch (err: any) {
      console.error(err);
      alert(err.message || "Ошибка при сохранении настроек");
    } finally {
      setSaving(false);
    }
  };

  const handleResetVacancies = async () => {
    if (!confirm("Вы уверены, что хотите сбросить статус всех найденных вакансий? Бот сможет заново просмотреть и откликнуться на подходящие.")) {
      return;
    }
    try {
      setResettingVacancies(true);
      const res = await resetUserVacancies();
      setResetMessage(res.message || "Вакансии сброшены");
      setTimeout(() => setResetMessage(null), 4000);
    } catch (err: any) {
      alert(err.message || "Ошибка при сбросе вакансий");
    } finally {
      setResettingVacancies(false);
    }
  };

  if (loading) {
    return <div className="text-slate-400 text-sm py-8">Загрузка настроек...</div>;
  }

  return (
    <form onSubmit={handleSaveAll} className="space-y-6 max-w-4xl pb-12">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Персональные настройки</h1>
          <p className="text-sm text-slate-400">
            Конфигурация поиска, AI-генератора откликов, прокси и безопасных лимитов
          </p>
        </div>

        <button
          type="submit"
          disabled={saving}
          className="flex items-center px-5 py-2.5 bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold rounded-xl shadow-lg shadow-blue-600/30 transition-all disabled:opacity-50"
        >
          {savedSuccess ? (
            <>
              <Check className="w-4 h-4 mr-2 text-emerald-300" />
              Сохранено!
            </>
          ) : (
            <>
              <Save className="w-4 h-4 mr-2" />
              {saving ? "Сохранение..." : "Сохранить все настройки"}
            </>
          )}
        </button>
      </div>

      {/* 1. HeadHunter Profile Connection */}
      <div className="bg-slate-800/80 border border-slate-700 rounded-2xl p-5 shadow space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2 text-white font-semibold">
            <Globe className="w-5 h-5 text-blue-400" />
            <h2>Подключение HeadHunter (hh.ru)</h2>
          </div>
          {onOpenHHLogin && (
            <button
              type="button"
              onClick={onOpenHHLogin}
              className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-blue-600/20 text-blue-400 border border-blue-500/30 hover:bg-blue-600/30 transition-all"
            >
              {userProfile?.hh_is_connected ? "Сменить аккаунт / Резюме" : "Подключить аккаунт"}
            </button>
          )}
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm bg-slate-900/60 p-4 rounded-xl border border-slate-800">
          <div>
            <span className="text-xs text-slate-400 block mb-1">Статус авторизации:</span>
            {userProfile?.hh_is_connected ? (
              <span className="inline-flex items-center text-emerald-400 font-semibold text-xs px-2.5 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20">
                <Check className="w-3.5 h-3.5 mr-1" />
                Авторизован ({userProfile.hh_phone})
              </span>
            ) : (
              <span className="text-rose-400 font-semibold text-xs">
                Не подключен (требуется вход по СМС)
              </span>
            )}
          </div>

          <div>
            <span className="text-xs text-slate-400 block mb-1">Выбранное резюме:</span>
            <span className="text-white font-medium text-xs">
              {userProfile?.selected_resume_title || "Не выбрано (будет использовано первое активное)"}
            </span>
          </div>
        </div>
      </div>

      {/* 2. Vacancy Search Filters */}
      <div className="bg-slate-800/80 border border-slate-700 rounded-2xl p-5 shadow space-y-4">
        <div className="flex items-center space-x-2 text-white font-semibold">
          <Search className="w-5 h-5 text-blue-400" />
          <h2>Фильтры поиска вакансий</h2>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
          <div className="sm:col-span-2">
            <label className="block text-xs font-medium text-slate-300 mb-1">
              Поисковый запрос (должность / ключевые слова)
            </label>
            <input
              type="text"
              value={userSettingsForm.search_query}
              onChange={(e) => handleUserSettingsChange("search_query", e.target.value)}
              placeholder="DevOps / Python Developer / Team Lead"
              className="w-full bg-slate-900 border border-slate-700 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:border-blue-500"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1">
              ID региона (1 = Москва, 2 = СПб, 113 = Россия)
            </label>
            <input
              type="number"
              value={userSettingsForm.search_region}
              onChange={(e) => handleUserSettingsChange("search_region", parseInt(e.target.value) || 1)}
              className="w-full bg-slate-900 border border-slate-700 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:border-blue-500"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1">
              Ожидаемая зарплата для анкет и тестов (руб.)
            </label>
            <input
              type="text"
              value={userSettingsForm.target_salary}
              onChange={(e) => handleUserSettingsChange("target_salary", e.target.value)}
              placeholder="180000"
              className="w-full bg-slate-900 border border-slate-700 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:border-blue-500 font-mono"
            />
            <p className="text-[11px] text-slate-400 mt-1">
              Бот автоматически ответит этой суммой на вопросы работодателей о зарплатных ожиданиях.
            </p>
          </div>
        </div>

        {/* Reset vacancies button */}
        <div className="pt-2 border-t border-slate-700/60 flex items-center justify-between">
          <div>
            <span className="text-xs text-slate-300 font-medium block">
              Сброс истории вакансий
            </span>
            <span className="text-[11px] text-slate-400">
              Позволяет заново обработать пропущенные или закрытые вакансии.
            </span>
          </div>

          <button
            type="button"
            onClick={handleResetVacancies}
            disabled={resettingVacancies}
            className="flex items-center px-3.5 py-1.5 text-xs font-semibold rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-200 transition-colors disabled:opacity-50"
          >
            <RotateCcw className={`w-3.5 h-3.5 mr-1.5 ${resettingVacancies ? "animate-spin" : ""}`} />
            {resettingVacancies ? "Сброс..." : "Сбросить историю"}
          </button>
        </div>
        {resetMessage && (
          <div className="text-xs text-emerald-400 font-mono">{resetMessage}</div>
        )}
      </div>

      {/* 3. Personal GigaChat & LLM Settings */}
      <div className="bg-slate-800/80 border border-slate-700 rounded-2xl p-5 shadow space-y-4">
        <div className="flex items-center space-x-2 text-white font-semibold">
          <Key className="w-5 h-5 text-purple-400" />
          <h2>Генератор сопроводительных писем (GigaChat API)</h2>
        </div>
        <p className="text-xs text-slate-400">
          Каждый пользователь использует собственный ключ GigaChat API для генерации уникальных персонализированных писем и распознавания капчи.
        </p>

        <div className="space-y-4 text-sm">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1">
                GigaChat Authorization Key (Base64)
              </label>
              <input
                type="password"
                placeholder={userProfile?.gigachat_auth_key_masked || "Вставьте Base64 токен из developers.sber.ru"}
                value={userSettingsForm.gigachat_auth_key}
                onChange={(e) => handleUserSettingsChange("gigachat_auth_key", e.target.value)}
                className="w-full bg-slate-900 border border-slate-700 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:border-blue-500 font-mono"
              />
              <p className="text-[11px] text-slate-500 mt-1">
                Оставьте пустым, если не хотите менять сохраненный ключ.
              </p>
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1">
                Тип аккаунта (Scope)
              </label>
              <select
                value={userSettingsForm.gigachat_scope}
                onChange={(e) => handleUserSettingsChange("gigachat_scope", e.target.value)}
                className="w-full bg-slate-900 border border-slate-700 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:border-blue-500"
              >
                <option value="GIGACHAT_API_PERS">Физическое лицо (GIGACHAT_API_PERS)</option>
                <option value="GIGACHAT_API_CORP">Юридическое лицо (GIGACHAT_API_CORP)</option>
              </select>
            </div>
          </div>
        </div>
      </div>

      {/* 4. Personal Proxy Settings (for Netherlands VPS) */}
      <div className="bg-slate-800/80 border border-slate-700 rounded-2xl p-5 shadow space-y-4">
        <div className="flex items-center space-x-2 text-white font-semibold">
          <Shield className="w-5 h-5 text-amber-400" />
          <h2>Прокси для обхода блокировок (Нидерланды VPS)</h2>
        </div>
        <p className="text-xs text-slate-400">
          HeadHunter и Сбербанк блокируют запросы из европейских дата-центров. Укажите российский прокси для бесперебойной работы.
        </p>

        <div>
          <label className="block text-xs font-medium text-slate-300 mb-1">
            HTTP или SOCKS5 Прокси
          </label>
          <input
            type="text"
            placeholder="http://user:password@ru-proxy-ip:port"
            value={userSettingsForm.proxy_url}
            onChange={(e) => handleUserSettingsChange("proxy_url", e.target.value)}
            className="w-full bg-slate-900 border border-slate-700 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:border-blue-500 font-mono"
          />
        </div>
      </div>

      {/* 5. Rate Limits Card */}
      <div className="bg-slate-800/80 border border-slate-700 rounded-2xl p-5 shadow space-y-4">
        <div className="flex items-center space-x-2 text-white font-semibold">
          <ShieldAlert className="w-5 h-5 text-emerald-400" />
          <h2>Лимиты безопасности и тайминги</h2>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1">
              Макс. откликов в час
            </label>
            <input
              type="number"
              value={formData.max_applications_per_hour ?? 20}
              onChange={(e) => handleGlobalChange("max_applications_per_hour", parseInt(e.target.value) || 1)}
              className="w-full bg-slate-900 border border-slate-700 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:border-blue-500"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1">
              Макс. откликов в день
            </label>
            <input
              type="number"
              min={1}
              value={formData.max_applications_per_day ?? 100}
              onChange={(e) => handleGlobalChange("max_applications_per_day", parseInt(e.target.value) || 1)}
              className="w-full bg-slate-900 border border-slate-700 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:border-blue-500"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1">
              Минимальная пауза между откликами (сек, мин. 15)
            </label>
            <input
              type="number"
              min={15}
              value={formData.min_delay_between_applies_sec ?? 15}
              onChange={(e) =>
                handleGlobalChange("min_delay_between_applies_sec", Math.max(15, parseInt(e.target.value) || 15))
              }
              className="w-full bg-slate-900 border border-slate-700 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:border-blue-500"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1">
              Интервал циклов поиска (минут)
            </label>
            <input
              type="number"
              min={5}
              value={formData.search_interval_minutes ?? 30}
              onChange={(e) => handleGlobalChange("search_interval_minutes", parseInt(e.target.value) || 10)}
              className="w-full bg-slate-900 border border-slate-700 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:border-blue-500"
            />
          </div>
        </div>
      </div>
    </form>
  );
};
