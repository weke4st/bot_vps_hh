import React, { useEffect, useState } from "react";
import {
  AlertCircle,
  Ban,
  Bot,
  Check,
  CheckCircle2,
  Clock,
  KeyRound,
  Lock,
  PauseCircle,
  Phone,
  Plus,
  RefreshCw,
  Search,
  Shield,
  ShieldAlert,
  Trash2,
  Unlock,
  UserCheck,
  UserPlus,
  Users,
  X,
} from "lucide-react";
import {
  adminApproveUser,
  adminCreateUser,
  adminDeleteUser,
  adminRejectUser,
  adminResetUserPassword,
  adminStopUserBot,
  adminToggleUserActive,
  adminUpdateSettings,
  fetchAdminUsers,
} from "../api";
import { AdminUserItem, AdminUsersListResponse, UserProfile } from "../types";

interface AdminPanelProps {
  currentUser: UserProfile;
  onPendingCountChange?: (count: number) => void;
}

export const AdminPanel: React.FC<AdminPanelProps> = ({
  currentUser,
  onPendingCountChange,
}) => {
  const [data, setData] = useState<AdminUsersListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [busyUserId, setBusyUserId] = useState<number | null>(null);

  // Create user modal state
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [newEmail, setNewEmail] = useState("");
  const [newName, setNewName] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newIsAdmin, setNewIsAdmin] = useState(false);
  const [creating, setCreating] = useState(false);

  // Reset password modal state
  const [resetTarget, setResetTarget] = useState<AdminUserItem | null>(null);
  const [resetPasswordVal, setResetPasswordVal] = useState("");
  const [resettingPw, setResettingPw] = useState(false);

  const loadData = async () => {
    try {
      setError(null);
      const res = await fetchAdminUsers();
      setData(res);
      onPendingCountChange?.(res.summary.pending_count);
    } catch (err: any) {
      setError(err.message || "Не удалось загрузить список пользователей");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3500);
  };

  const runUserAction = async (userId: number, action: () => Promise<{ message: string }>) => {
    try {
      setBusyUserId(userId);
      setError(null);
      const res = await action();
      showToast(res.message);
      await loadData();
    } catch (err: any) {
      setError(err.message || "Не удалось выполнить действие");
    } finally {
      setBusyUserId(null);
    }
  };

  const handleToggleRegistrationMode = async () => {
    if (!data) return;
    try {
      setError(null);
      const next = !data.allow_registration_requests;
      const res = await adminUpdateSettings(next);
      showToast(res.message);
      await loadData();
    } catch (err: any) {
      setError(err.message || "Не удалось обновить политику регистрации");
    }
  };

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setCreating(true);
      setError(null);
      await adminCreateUser({
        email: newEmail,
        password: newPassword,
        full_name: newName,
        is_admin: newIsAdmin,
      });
      setIsCreateOpen(false);
      setNewEmail("");
      setNewName("");
      setNewPassword("");
      setNewIsAdmin(false);
      showToast("Пользователь успешно создан и активирован");
      await loadData();
    } catch (err: any) {
      setError(err.message || "Не удалось создать пользователя");
    } finally {
      setCreating(false);
    }
  };

  const handleResetPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!resetTarget) return;
    try {
      setResettingPw(true);
      setError(null);
      const res = await adminResetUserPassword(resetTarget.id, resetPasswordVal);
      setResetTarget(null);
      setResetPasswordVal("");
      showToast(res.message);
    } catch (err: any) {
      setError(err.message || "Не удалось сменить пароль");
    } finally {
      setResettingPw(false);
    }
  };

  const handleDeleteUser = async (u: AdminUserItem) => {
    if (
      !window.confirm(
        `Удалить пользователя ${u.email} и все его отклики, настройки и сессию hh.ru? Это действие необратимо.`
      )
    ) {
      return;
    }
    await runUserAction(u.id, () => adminDeleteUser(u.id));
  };

  const formatDate = (iso?: string | null) => {
    if (!iso) return "—";
    try {
      return new Date(iso).toLocaleString("ru-RU", {
        timeZone: "Europe/Moscow",
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return iso;
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-slate-400 text-sm">
        <RefreshCw className="w-5 h-5 mr-2 animate-spin text-blue-400" />
        Загрузка панели администратора...
      </div>
    );
  }

  const users = data?.users || [];
  const pendingUsers = users.filter((u) => u.approval_status === "pending");
  const filteredUsers = users.filter((u) => {
    const q = search.trim().toLowerCase();
    if (!q) return true;
    return (
      u.email.toLowerCase().includes(q) ||
      (u.full_name || "").toLowerCase().includes(q) ||
      (u.hh_phone || "").toLowerCase().includes(q)
    );
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2.5">
            <Shield className="w-6 h-6 text-blue-400" />
            <span>Панель администратора</span>
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Управление пользователями, одобрение заявок на доступ и контроль ботов
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <button
            onClick={loadData}
            className="px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium border border-slate-700 flex items-center gap-1.5 transition-colors"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            <span>Обновить</span>
          </button>
          <button
            onClick={() => setIsCreateOpen(true)}
            className="px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold shadow-lg shadow-blue-600/20 flex items-center gap-1.5 transition-all"
          >
            <Plus className="w-4 h-4" />
            <span>Создать пользователя</span>
          </button>
        </div>
      </div>

      {/* Feedback banners */}
      {error && (
        <div className="p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/30 flex items-center justify-between text-rose-300 text-sm">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 flex-shrink-0 text-rose-400" />
            <span>{error}</span>
          </div>
          <button onClick={() => setError(null)} className="text-rose-400 hover:text-white">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {toast && (
        <div className="p-3.5 rounded-xl bg-emerald-500/10 border border-emerald-500/30 flex items-center gap-2 text-emerald-300 text-sm">
          <CheckCircle2 className="w-4 h-4 flex-shrink-0 text-emerald-400" />
          <span>{toast}</span>
        </div>
      )}

      {/* Summary Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-4">
          <div className="flex items-center justify-between text-slate-400 text-xs mb-2">
            <span>Всего пользователей</span>
            <Users className="w-4 h-4 text-blue-400" />
          </div>
          <div className="text-2xl font-bold text-white">{data?.summary.total_users ?? 0}</div>
        </div>

        <div
          className={`border rounded-2xl p-4 ${
            (data?.summary.pending_count ?? 0) > 0
              ? "bg-amber-500/10 border-amber-500/40"
              : "bg-slate-900/90 border-slate-800"
          }`}
        >
          <div className="flex items-center justify-between text-slate-400 text-xs mb-2">
            <span>Ожидают одобрения</span>
            <Clock
              className={`w-4 h-4 ${
                (data?.summary.pending_count ?? 0) > 0 ? "text-amber-400" : "text-slate-500"
              }`}
            />
          </div>
          <div className="text-2xl font-bold text-white">{data?.summary.pending_count ?? 0}</div>
        </div>

        <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-4">
          <div className="flex items-center justify-between text-slate-400 text-xs mb-2">
            <span>Активных ботов</span>
            <Bot className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-2xl font-bold text-white">{data?.summary.active_bots_count ?? 0}</div>
        </div>

        <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-4">
          <div className="flex items-center justify-between text-slate-400 text-xs mb-2">
            <span>Откликов всего</span>
            <UserCheck className="w-4 h-4 text-purple-400" />
          </div>
          <div className="text-2xl font-bold text-white">
            {data?.summary.total_applications ?? 0}
          </div>
        </div>
      </div>

      {/* Security & Registration Mode Card */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-5 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="flex items-start gap-3">
          <div className="p-2.5 rounded-xl bg-blue-500/10 text-blue-400 border border-blue-500/20">
            {data?.allow_registration_requests ? (
              <Shield className="w-5 h-5" />
            ) : (
              <Lock className="w-5 h-5 text-amber-400" />
            )}
          </div>
          <div>
            <h3 className="text-sm font-semibold text-white">
              Режим приёма новых пользователей
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">
              {data?.allow_registration_requests
                ? "Включён режим заявок: новые пользователи могут подать запрос, но войти смогут только после вашего одобрения."
                : "Закрытый режим: публичные заявки отключены, создавать новые аккаунты можете только вы через кнопку «Создать пользователя»."}
            </p>
          </div>
        </div>

        <button
          onClick={handleToggleRegistrationMode}
          className={`px-4 py-2 rounded-xl text-xs font-semibold border transition-all whitespace-nowrap ${
            data?.allow_registration_requests
              ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/30 hover:bg-emerald-500/25"
              : "bg-amber-500/15 text-amber-300 border-amber-500/30 hover:bg-amber-500/25"
          }`}
        >
          {data?.allow_registration_requests
            ? "Заявки: Включены (Нажмите чтобы закрыть)"
            : "Заявки: Закрыты (Нажмите чтобы открыть)"}
        </button>
      </div>

      {/* Pending Approval Queue */}
      {pendingUsers.length > 0 && (
        <div className="bg-amber-500/5 border border-amber-500/30 rounded-2xl p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-bold text-amber-300 flex items-center gap-2">
              <ShieldAlert className="w-5 h-5" />
              <span>Новые заявки на регистрацию ({pendingUsers.length})</span>
            </h2>
          </div>

          <div className="grid gap-3">
            {pendingUsers.map((u) => (
              <div
                key={u.id}
                className="bg-slate-900/95 border border-slate-800 rounded-xl p-4 flex flex-col md:flex-row md:items-center md:justify-between gap-4"
              >
                <div className="space-y-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-semibold text-white text-sm">
                      {u.full_name || "Без имени"}
                    </span>
                    <span className="text-xs font-mono text-blue-300 bg-blue-500/10 px-2 py-0.5 rounded">
                      {u.email}
                    </span>
                    <span className="text-[11px] text-slate-500">
                      Подана: {formatDate(u.created_at)}
                    </span>
                  </div>
                  {u.registration_note && (
                    <p className="text-xs text-slate-300 bg-slate-950/70 px-3 py-1.5 rounded-lg border border-slate-800/80 inline-block">
                      Комментарий: {u.registration_note}
                    </p>
                  )}
                </div>

                <div className="flex items-center gap-2 flex-shrink-0">
                  <button
                    disabled={busyUserId === u.id}
                    onClick={() => runUserAction(u.id, () => adminApproveUser(u.id))}
                    className="px-3.5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold flex items-center gap-1.5 transition-colors disabled:opacity-50"
                  >
                    <Check className="w-3.5 h-3.5" />
                    <span>Одобрить</span>
                  </button>
                  <button
                    disabled={busyUserId === u.id}
                    onClick={() => runUserAction(u.id, () => adminRejectUser(u.id))}
                    className="px-3.5 py-2 rounded-xl bg-rose-600/20 hover:bg-rose-600/30 text-rose-300 border border-rose-500/30 text-xs font-semibold flex items-center gap-1.5 transition-colors disabled:opacity-50"
                  >
                    <Ban className="w-3.5 h-3.5" />
                    <span>Отклонить</span>
                  </button>
                  <button
                    disabled={busyUserId === u.id}
                    onClick={() => handleDeleteUser(u)}
                    className="p-2 rounded-xl text-slate-400 hover:text-rose-400 hover:bg-slate-800 transition-colors"
                    title="Удалить заявку"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Users Table */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-2xl overflow-hidden">
        <div className="p-4 border-b border-slate-800 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <h2 className="text-sm font-bold text-white">Все пользователи платформы</h2>
          <div className="relative w-full sm:w-72">
            <Search className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Поиск по email, имени или телефону..."
              className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-9 pr-3 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-blue-500"
            />
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-slate-800/80 text-[11px] uppercase tracking-wider text-slate-400 bg-slate-950/50">
                <th className="py-3 px-4">Пользователь</th>
                <th className="py-3 px-4">Доступ</th>
                <th className="py-3 px-4">HeadHunter</th>
                <th className="py-3 px-4">Бот / Ключи</th>
                <th className="py-3 px-4 text-right">Отклики</th>
                <th className="py-3 px-4 text-right">Управление</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-xs">
              {filteredUsers.map((u) => {
                const isSelf = u.id === currentUser.id;
                return (
                  <tr key={u.id} className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-3.5 px-4">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-white">
                          {u.full_name || "Без имени"}
                        </span>
                        {u.is_admin && (
                          <span className="px-1.5 py-0.5 rounded bg-blue-500/20 text-blue-300 border border-blue-500/30 text-[10px] font-semibold">
                            Admin
                          </span>
                        )}
                        {isSelf && (
                          <span className="text-[10px] text-slate-500">(Вы)</span>
                        )}
                      </div>
                      <div className="text-slate-400 font-mono text-[11px] mt-0.5">
                        #{u.id} · {u.email}
                      </div>
                      <div className="text-slate-500 text-[10px] mt-0.5">
                        Создан: {formatDate(u.created_at)}
                      </div>
                    </td>

                    <td className="py-3.5 px-4">
                      {u.approval_status === "pending" ? (
                        <span className="inline-flex items-center gap-1 px-2 py-1 rounded-lg bg-amber-500/15 text-amber-300 border border-amber-500/30 font-medium">
                          <Clock className="w-3 h-3" /> Ожидает
                        </span>
                      ) : u.approval_status === "rejected" ? (
                        <span className="inline-flex items-center gap-1 px-2 py-1 rounded-lg bg-rose-500/15 text-rose-300 border border-rose-500/30 font-medium">
                          <Ban className="w-3 h-3" /> Отклонён
                        </span>
                      ) : u.is_active ? (
                        <span className="inline-flex items-center gap-1 px-2 py-1 rounded-lg bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 font-medium">
                          <CheckCircle2 className="w-3 h-3" /> Активен
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2 py-1 rounded-lg bg-rose-500/15 text-rose-300 border border-rose-500/30 font-medium">
                          <Lock className="w-3 h-3" /> Заблокирован
                        </span>
                      )}
                    </td>

                    <td className="py-3.5 px-4">
                      {u.hh_is_connected ? (
                        <span className="inline-flex items-center gap-1.5 text-emerald-300 font-mono">
                          <Phone className="w-3.5 h-3.5 text-emerald-400" />
                          {u.hh_phone || "Подключён"}
                        </span>
                      ) : (
                        <span className="text-slate-500">Не подключён</span>
                      )}
                    </td>

                    <td className="py-3.5 px-4 space-y-1">
                      <div className="flex items-center gap-1.5">
                        <span
                          className={`w-2 h-2 rounded-full ${
                            u.bot_enabled ? "bg-emerald-400 animate-pulse" : "bg-slate-600"
                          }`}
                        />
                        <span className={u.bot_enabled ? "text-emerald-300 font-medium" : "text-slate-400"}>
                          {u.bot_enabled ? "Включён" : "Остановлен"}
                        </span>
                      </div>
                      <div className="flex items-center gap-1.5 text-[10px]">
                        <span
                          className={`px-1.5 py-0.5 rounded ${
                            u.has_gigachat_key
                              ? "bg-slate-800 text-emerald-300"
                              : "bg-slate-800 text-slate-500"
                          }`}
                        >
                          {u.has_gigachat_key ? "GigaChat ✓" : "Нет ключа"}
                        </span>
                        {u.has_proxy && (
                          <span className="px-1.5 py-0.5 rounded bg-slate-800 text-blue-300">
                            Proxy ✓
                          </span>
                        )}
                      </div>
                    </td>

                    <td className="py-3.5 px-4 text-right font-mono font-semibold text-white">
                      {u.applications_count}
                    </td>

                    <td className="py-3.5 px-4">
                      <div className="flex items-center justify-end gap-1.5">
                        {u.approval_status !== "approved" && (
                          <button
                            disabled={busyUserId === u.id}
                            onClick={() => runUserAction(u.id, () => adminApproveUser(u.id))}
                            className="p-1.5 rounded-lg bg-emerald-600/20 text-emerald-300 hover:bg-emerald-600/30 border border-emerald-500/30"
                            title="Одобрить доступ"
                          >
                            <Check className="w-3.5 h-3.5" />
                          </button>
                        )}

                        {u.bot_enabled && (
                          <button
                            disabled={busyUserId === u.id}
                            onClick={() => runUserAction(u.id, () => adminStopUserBot(u.id))}
                            className="p-1.5 rounded-lg bg-amber-500/15 text-amber-300 hover:bg-amber-500/25 border border-amber-500/30"
                            title="Принудительно остановить бота"
                          >
                            <PauseCircle className="w-3.5 h-3.5" />
                          </button>
                        )}

                        {!isSelf && u.approval_status === "approved" && (
                          <button
                            disabled={busyUserId === u.id}
                            onClick={() => runUserAction(u.id, () => adminToggleUserActive(u.id))}
                            className={`p-1.5 rounded-lg border transition-colors ${
                              u.is_active
                                ? "bg-slate-800 text-amber-300 hover:bg-amber-500/20 border-slate-700"
                                : "bg-emerald-500/15 text-emerald-300 hover:bg-emerald-500/25 border-emerald-500/30"
                            }`}
                            title={u.is_active ? "Заблокировать пользователя" : "Разблокировать"}
                          >
                            {u.is_active ? (
                              <Lock className="w-3.5 h-3.5" />
                            ) : (
                              <Unlock className="w-3.5 h-3.5" />
                            )}
                          </button>
                        )}

                        <button
                          disabled={busyUserId === u.id}
                          onClick={() => {
                            setResetTarget(u);
                            setResetPasswordVal("");
                          }}
                          className="p-1.5 rounded-lg bg-slate-800 text-slate-300 hover:text-blue-300 hover:bg-slate-700 border border-slate-700"
                          title="Сменить пароль"
                        >
                          <KeyRound className="w-3.5 h-3.5" />
                        </button>

                        {!isSelf && (
                          <button
                            disabled={busyUserId === u.id}
                            onClick={() => handleDeleteUser(u)}
                            className="p-1.5 rounded-lg bg-slate-800 text-slate-400 hover:text-rose-400 hover:bg-rose-500/15 border border-slate-700"
                            title="Удалить пользователя"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}

              {filteredUsers.length === 0 && (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-slate-500 text-sm">
                    Пользователи не найдены
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Create User Modal */}
      {isCreateOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-md p-6 shadow-2xl relative">
            <button
              onClick={() => setIsCreateOpen(false)}
              className="absolute top-4 right-4 text-slate-400 hover:text-white p-1"
            >
              <X className="w-5 h-5" />
            </button>

            <div className="flex items-center gap-3 mb-5">
              <div className="p-2.5 rounded-xl bg-blue-600/20 text-blue-400">
                <UserPlus className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-lg font-bold text-white">Создать пользователя</h3>
                <p className="text-xs text-slate-400">
                  Аккаунт сразу будет одобрен и активирован
                </p>
              </div>
            </div>

            <form onSubmit={handleCreateUser} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Имя</label>
                <input
                  type="text"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="Алексей"
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2.5 text-sm text-white focus:outline-none focus:border-blue-500"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Email</label>
                <input
                  type="email"
                  required
                  value={newEmail}
                  onChange={(e) => setNewEmail(e.target.value)}
                  placeholder="user@domain.com"
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2.5 text-sm text-white focus:outline-none focus:border-blue-500"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Пароль</label>
                <input
                  type="password"
                  required
                  minLength={6}
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="Минимум 6 символов"
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2.5 text-sm text-white focus:outline-none focus:border-blue-500"
                />
              </div>
              <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={newIsAdmin}
                  onChange={(e) => setNewIsAdmin(e.target.checked)}
                  className="rounded border-slate-700 bg-slate-950 text-blue-600 focus:ring-blue-500"
                />
                <span>Выдать права администратора</span>
              </label>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setIsCreateOpen(false)}
                  className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium"
                >
                  Отмена
                </button>
                <button
                  type="submit"
                  disabled={creating}
                  className="px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold disabled:opacity-50"
                >
                  {creating ? "Создание..." : "Создать аккаунт"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Reset Password Modal */}
      {resetTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-sm p-6 shadow-2xl relative">
            <button
              onClick={() => setResetTarget(null)}
              className="absolute top-4 right-4 text-slate-400 hover:text-white p-1"
            >
              <X className="w-5 h-5" />
            </button>

            <h3 className="text-base font-bold text-white mb-1">Сменить пароль</h3>
            <p className="text-xs text-slate-400 mb-4 font-mono">{resetTarget.email}</p>

            <form onSubmit={handleResetPassword} className="space-y-4">
              <input
                type="password"
                required
                minLength={6}
                value={resetPasswordVal}
                onChange={(e) => setResetPasswordVal(e.target.value)}
                placeholder="Новый пароль (мин. 6 символов)"
                className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2.5 text-sm text-white focus:outline-none focus:border-blue-500"
              />
              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setResetTarget(null)}
                  className="px-3.5 py-2 rounded-xl bg-slate-800 text-slate-300 text-xs"
                >
                  Отмена
                </button>
                <button
                  type="submit"
                  disabled={resettingPw}
                  className="px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold disabled:opacity-50"
                >
                  {resettingPw ? "Сохранение..." : "Сохранить"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
