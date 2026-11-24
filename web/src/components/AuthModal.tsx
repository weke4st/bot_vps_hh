import React, { useEffect, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  Lock,
  LogIn,
  Mail,
  MessageSquare,
  ShieldCheck,
  User as UserIcon,
  UserPlus,
  X,
} from "lucide-react";
import { fetchAuthConfig, loginUser, registerUser } from "../api";
import { RegistrationMode } from "../types";

interface AuthModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (user: any) => void;
}

export const AuthModal: React.FC<AuthModalProps> = ({ isOpen, onClose, onSuccess }) => {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [registrationMode, setRegistrationMode] = useState<RegistrationMode>("request");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pendingMessage, setPendingMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    fetchAuthConfig()
      .then((cfg) => {
        setRegistrationMode(cfg.registration_mode);
        if (cfg.registration_mode === "first_admin") {
          setMode("register");
        } else if (cfg.registration_mode === "closed") {
          setMode("login");
        }
      })
      .catch(() => {});
  }, [isOpen]);

  if (!isOpen) return null;

  const switchMode = (nextMode: "login" | "register") => {
    setMode(nextMode);
    setError(null);
    setPendingMessage(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setPendingMessage(null);
    setLoading(true);

    try {
      if (mode === "login") {
        const data = await loginUser(email, password);
        onSuccess(data.user);
        onClose();
      } else {
        const data = await registerUser(email, password, fullName, note);
        if (data.status === "approved" && data.user) {
          onSuccess(data.user);
          onClose();
        } else {
          setPendingMessage(
            data.message ||
              "Заявка отправлена администратору! Доступ откроется после одобрения."
          );
          setPassword("");
          setNote("");
        }
      }
    } catch (err: any) {
      setError(err.message || "Ошибка авторизации");
    } finally {
      setLoading(false);
    }
  };

  const isFirstAdmin = registrationMode === "first_admin";
  const isClosed = registrationMode === "closed";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-fade-in">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-md p-6 shadow-2xl relative">
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-slate-400 hover:text-white p-1 rounded-lg transition-colors"
          aria-label="Закрыть"
        >
          <X className="w-5 h-5" />
        </button>

        <div className="flex items-center space-x-3 mb-6">
          <div className="p-3 bg-blue-600/20 text-blue-400 rounded-xl">
            {mode === "login" ? (
              <LogIn className="w-6 h-6" />
            ) : isFirstAdmin ? (
              <ShieldCheck className="w-6 h-6" />
            ) : (
              <UserPlus className="w-6 h-6" />
            )}
          </div>
          <div>
            <h2 className="text-xl font-bold text-white tracking-tight">
              {mode === "login"
                ? "Вход в аккаунт"
                : isFirstAdmin
                ? "Настройка администратора"
                : "Заявка на доступ"}
            </h2>
            <p className="text-xs text-slate-400">
              {mode === "login"
                ? "Войдите для управления вашим ботом hh.ru"
                : isFirstAdmin
                ? "Первый пользователь становится администратором платформы"
                : "Отправьте запрос — администратор проверит и откроет доступ"}
            </p>
          </div>
        </div>

        {error && (
          <div className="mb-4 p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 flex items-start space-x-2 text-rose-400 text-sm">
            <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        {pendingMessage && (
          <div className="mb-4 p-3.5 rounded-xl bg-emerald-500/10 border border-emerald-500/30 flex items-start space-x-2.5 text-emerald-300 text-sm">
            <CheckCircle2 className="w-5 h-5 flex-shrink-0 mt-0.5 text-emerald-400" />
            <div>
              <p className="font-semibold text-emerald-200">Заявка принята</p>
              <p className="text-xs text-emerald-300/90 mt-0.5">{pendingMessage}</p>
            </div>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          {mode === "register" && (
            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1">Ваше имя</label>
              <div className="relative">
                <UserIcon className="w-4 h-4 text-slate-500 absolute left-3 top-3" />
                <input
                  type="text"
                  required
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  placeholder="Иван Иванов"
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-9 pr-4 py-2.5 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-blue-500"
                />
              </div>
            </div>
          )}

          <div>
            <label className="block text-xs font-semibold text-slate-300 mb-1">Email</label>
            <div className="relative">
              <Mail className="w-4 h-4 text-slate-500 absolute left-3 top-3" />
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@domain.com"
                className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-9 pr-4 py-2.5 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-blue-500"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-300 mb-1">Пароль</label>
            <div className="relative">
              <Lock className="w-4 h-4 text-slate-500 absolute left-3 top-3" />
              <input
                type="password"
                required
                minLength={6}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Минимум 6 символов"
                className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-9 pr-4 py-2.5 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-blue-500"
              />
            </div>
          </div>

          {mode === "register" && !isFirstAdmin && (
            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1">
                Комментарий / контакт для админа (необязательно)
              </label>
              <div className="relative">
                <MessageSquare className="w-4 h-4 text-slate-500 absolute left-3 top-3" />
                <input
                  type="text"
                  maxLength={500}
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="Напр.: @telegram или зачем нужен доступ"
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-9 pr-4 py-2.5 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-blue-500"
                />
              </div>
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full mt-2 py-3 px-4 rounded-xl bg-blue-600 hover:bg-blue-500 font-semibold text-sm text-white shadow-lg shadow-blue-600/20 transition-all flex items-center justify-center space-x-2 disabled:opacity-50"
          >
            {loading ? (
              <span className="animate-spin w-4 h-4 border-2 border-white border-t-transparent rounded-full" />
            ) : mode === "login" ? (
              <>
                <LogIn className="w-4 h-4" />
                <span>Войти</span>
              </>
            ) : isFirstAdmin ? (
              <>
                <ShieldCheck className="w-4 h-4" />
                <span>Создать администратора</span>
              </>
            ) : (
              <>
                <Clock className="w-4 h-4" />
                <span>Отправить заявку на доступ</span>
              </>
            )}
          </button>
        </form>

        <div className="mt-6 pt-4 border-t border-slate-800/80 text-center text-xs text-slate-400">
          {isClosed ? (
            <div className="flex items-center justify-center space-x-1.5 text-slate-500">
              <Lock className="w-3.5 h-3.5" />
              <span>Регистрация закрыта — аккаунты создаёт только администратор</span>
            </div>
          ) : mode === "login" ? (
            <>
              Нет аккаунта?{" "}
              <button
                type="button"
                onClick={() => switchMode("register")}
                className="text-blue-400 hover:underline font-semibold"
              >
                {isFirstAdmin ? "Создать администратора" : "Подать заявку на доступ"}
              </button>
            </>
          ) : (
            <>
              Уже одобрен аккаунт?{" "}
              <button
                type="button"
                onClick={() => switchMode("login")}
                className="text-blue-400 hover:underline font-semibold"
              >
                Войти
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
};
