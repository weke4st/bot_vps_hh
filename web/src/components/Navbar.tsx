import React from "react";
import {
  Activity,
  Bot,
  CheckCircle,
  FileSpreadsheet,
  FileText,
  LogOut,
  Pause,
  Phone,
  Play,
  Settings as SettingsIcon,
  Shield,
  Terminal,
  User,
} from "lucide-react";
import { BotStatus, UserProfile } from "../types";

interface NavbarProps {
  currentTab: string;
  onTabChange: (tab: string) => void;
  botStatus: BotStatus | null;
  currentUser: UserProfile | null;
  pendingAdminCount?: number;
  onToggleBot: () => void;
  onOpenHHLogin: () => void;
  onLogout: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  currentTab,
  onTabChange,
  botStatus,
  currentUser,
  pendingAdminCount = 0,
  onToggleBot,
  onOpenHHLogin,
  onLogout,
}) => {
  const isBotEnabled = currentUser?.bot_enabled ?? botStatus?.is_running ?? false;
  const isHHConnected = currentUser?.hh_is_connected ?? false;

  const tabs = [
    { id: "dashboard", label: "Дашборд", icon: Activity, badge: 0 },
    { id: "applications", label: "Отклики", icon: FileSpreadsheet, badge: 0 },
    { id: "settings", label: "Настройки", icon: SettingsIcon, badge: 0 },
    { id: "resume", label: "Резюме", icon: FileText, badge: 0 },
    { id: "logs", label: "Логи (Live)", icon: Terminal, badge: 0 },
    ...(currentUser?.is_admin
      ? [{ id: "admin", label: "Админка", icon: Shield, badge: pendingAdminCount }]
      : []),
  ];

  return (
    <header className="border-b border-slate-800 bg-slate-900/95 backdrop-blur sticky top-0 z-40">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo & title */}
          <div className="flex items-center space-x-3">
            <div className="p-2 bg-blue-600/20 text-blue-400 rounded-lg border border-blue-500/30">
              <Bot className="w-6 h-6" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="font-bold text-lg text-white tracking-tight">HH Cloud Auto-Apply</span>
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-900/60 text-blue-300 font-mono">
                  SaaS Multi-User
                </span>
              </div>
            </div>
          </div>

          {/* Navigation Links */}
          <nav className="hidden md:flex space-x-1">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              const active = currentTab === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => onTabChange(tab.id)}
                  className={`flex items-center px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                    active
                      ? "bg-slate-800 text-blue-400 border border-slate-700"
                      : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50"
                  }`}
                >
                  <Icon className="w-4 h-4 mr-2" />
                  <span>{tab.label}</span>
                  {tab.badge > 0 && (
                    <span className="ml-1.5 px-1.5 py-0.5 text-[10px] font-bold rounded-full bg-amber-500 text-slate-950">
                      {tab.badge}
                    </span>
                  )}
                </button>
              );
            })}
          </nav>

          {/* User Status & Controls */}
          <div className="flex items-center space-x-2.5">
            {/* HH Connection Status Button */}
            {isHHConnected ? (
              <button
                onClick={onOpenHHLogin}
                className="flex items-center px-3 py-1.5 rounded-lg text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/20 transition-all"
                title="HH подключен. Нажмите для смены аккаунта"
              >
                <CheckCircle className="w-3.5 h-3.5 mr-1.5 text-emerald-400" />
                <span className="font-mono">{currentUser?.hh_phone || "HH подключен"}</span>
              </button>
            ) : (
              <button
                onClick={onOpenHHLogin}
                className="flex items-center px-3 py-1.5 rounded-lg text-xs font-semibold bg-amber-500/20 text-amber-300 border border-amber-500/40 hover:bg-amber-500/30 transition-all animate-pulse"
                title="Нажмите для привязки вашего номера hh.ru"
              >
                <Phone className="w-3.5 h-3.5 mr-1.5 text-amber-400" />
                Подключить HH
              </button>
            )}

            {/* Bot Play/Pause Button */}
            <button
              onClick={onToggleBot}
              className={`flex items-center px-3.5 py-1.5 rounded-lg text-xs font-semibold shadow transition-all ${
                isBotEnabled
                  ? "bg-rose-600 hover:bg-rose-500 text-white shadow-rose-600/30"
                  : "bg-emerald-600 hover:bg-emerald-500 text-white shadow-emerald-600/30"
              }`}
              title={isBotEnabled ? "Приостановить авто-отклики" : "Включить авто-отклики"}
            >
              {isBotEnabled ? (
                <>
                  <Pause className="w-3.5 h-3.5 mr-1" />
                  Остановить
                </>
              ) : (
                <>
                  <Play className="w-3.5 h-3.5 mr-1" />
                  Запустить
                </>
              )}
            </button>

            {/* User Profile / Logout */}
            {currentUser && (
              <div className="flex items-center pl-2 border-l border-slate-800 space-x-2">
                <div className="flex items-center space-x-1.5 text-xs text-slate-300">
                  <div className="w-6 h-6 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-400">
                    <User className="w-3.5 h-3.5" />
                  </div>
                  <span className="hidden lg:inline text-slate-300 font-medium">
                    {currentUser.full_name || currentUser.email}
                  </span>
                </div>
                <button
                  onClick={onLogout}
                  className="p-1.5 text-slate-400 hover:text-rose-400 rounded-lg hover:bg-slate-800 transition-colors"
                  title="Выйти из аккаунта"
                >
                  <LogOut className="w-4 h-4" />
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Mobile Navigation */}
        <nav className="flex md:hidden items-center space-x-1 pb-2 overflow-x-auto">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const active = currentTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => onTabChange(tab.id)}
                className={`flex items-center px-2.5 py-1.5 rounded-md text-xs font-medium whitespace-nowrap transition-colors ${
                  active
                    ? "bg-slate-800 text-blue-400 border border-slate-700"
                    : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50"
                }`}
              >
                <Icon className="w-3.5 h-3.5 mr-1.5" />
                <span>{tab.label}</span>
                {tab.badge > 0 && (
                  <span className="ml-1 px-1.5 py-0.2 text-[10px] font-bold rounded-full bg-amber-500 text-slate-950">
                    {tab.badge}
                  </span>
                )}
              </button>
            );
          })}
        </nav>
      </div>
    </header>
  );
};
