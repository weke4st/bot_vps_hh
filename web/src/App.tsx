import React, { useEffect, useState } from "react";
import {
  fetchBotStatus,
  fetchCurrentUser,
  logoutUser,
  toggleUserBot,
} from "./api";
import { Applications } from "./components/Applications";
import { AuthModal } from "./components/AuthModal";
import { Dashboard } from "./components/Dashboard";
import { HHLoginWizardModal } from "./components/HHLoginWizardModal";
import { Logs } from "./components/Logs";
import { Navbar } from "./components/Navbar";
import { Resume } from "./components/Resume";
import { Settings } from "./components/Settings";
import { BotStatus, LogEntry, UserProfile } from "./types";

export const App: React.FC = () => {
  const [currentTab, setCurrentTab] = useState<string>("dashboard");
  const [botStatus, setBotStatus] = useState<BotStatus | null>(null);
  const [currentUser, setCurrentUser] = useState<UserProfile | null>(null);
  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);
  const [isHHWizardOpen, setIsHHWizardOpen] = useState(false);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [wsConnected, setWsConnected] = useState(false);

  // Check auth & fetch user profile
  const reloadUserProfile = async () => {
    try {
      const user = await fetchCurrentUser();
      setCurrentUser(user);
      setIsAuthModalOpen(false);
    } catch (err) {
      setCurrentUser(null);
      setIsAuthModalOpen(true);
    }
  };

  useEffect(() => {
    reloadUserProfile();
    fetchBotStatus()
      .then(setBotStatus)
      .catch((err) => console.error("Initial status check failed", err));
  }, []);

  // Establish persistent WebSocket connection for real-time updates
  useEffect(() => {
    let ws: WebSocket | null = null;
    let reconnectTimer: any = null;

    const connectWS = () => {
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const host = window.location.host;
      const wsUrl = `${protocol}//${host}/api/ws`;

      ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        setWsConnected(true);
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "bot_status") {
            setBotStatus(msg.data);
          } else if (msg.type === "logs_snapshot") {
            setLogs(msg.data || []);
          } else if (msg.type === "log") {
            setLogs((prev) => [...prev.slice(-499), msg.data]);
          }
        } catch (err) {
          console.error("WS message parse error:", err);
        }
      };

      ws.onclose = () => {
        setWsConnected(false);
        reconnectTimer = setTimeout(connectWS, 3000);
      };

      ws.onerror = () => {
        setWsConnected(false);
      };
    };

    connectWS();

    return () => {
      if (ws) ws.close();
      if (reconnectTimer) clearTimeout(reconnectTimer);
    };
  }, []);

  const handleToggleBot = async () => {
    try {
      await toggleUserBot();
      await reloadUserProfile();
      const updated = await fetchBotStatus();
      setBotStatus(updated);
    } catch (err: any) {
      console.error(err);
      alert(err.message || "Не удалось переключить состояние бота");
    }
  };

  const handleLogout = async () => {
    await logoutUser();
    setCurrentUser(null);
    setIsAuthModalOpen(true);
  };

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100 flex flex-col font-['Inter',sans-serif]">
      <Navbar
        currentTab={currentTab}
        onTabChange={setCurrentTab}
        botStatus={botStatus}
        currentUser={currentUser}
        onToggleBot={handleToggleBot}
        onOpenHHLogin={() => setIsHHWizardOpen(true)}
        onLogout={handleLogout}
      />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* Banner if HH not connected */}
        {currentUser && !currentUser.hh_is_connected && (
          <div className="mb-6 p-4 rounded-2xl bg-amber-500/10 border border-amber-500/30 flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <span className="text-xl">⚠️</span>
              <div>
                <h4 className="text-sm font-bold text-amber-300">
                  Аккаунт HeadHunter не подключен
                </h4>
                <p className="text-xs text-amber-200/80">
                  Чтобы бот мог отправлять отклики от вашего имени, подключите номер телефона через СМС-код.
                </p>
              </div>
            </div>
            <button
              onClick={() => setIsHHWizardOpen(true)}
              className="px-4 py-2 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs rounded-xl shadow-md transition-colors whitespace-nowrap"
            >
              Подключить HH
            </button>
          </div>
        )}

        {currentTab === "dashboard" && <Dashboard />}
        {currentTab === "applications" && <Applications />}
        {currentTab === "settings" && (
          <Settings
            currentUser={currentUser}
            onOpenHHLogin={() => setIsHHWizardOpen(true)}
            onUserUpdated={reloadUserProfile}
          />
        )}
        {currentTab === "resume" && <Resume />}
        {currentTab === "logs" && (
          <Logs
            logs={logs}
            onClearLogs={() => setLogs([])}
            connected={wsConnected}
          />
        )}
      </main>

      {/* Auth Modal (Login / Register) */}
      <AuthModal
        isOpen={isAuthModalOpen}
        onClose={() => {
          if (currentUser) setIsAuthModalOpen(false);
        }}
        onSuccess={(user) => {
          setCurrentUser(user);
          setIsAuthModalOpen(false);
        }}
      />

      {/* HH.ru SMS Login Wizard Modal */}
      <HHLoginWizardModal
        isOpen={isHHWizardOpen}
        onClose={() => setIsHHWizardOpen(false)}
        onSuccess={reloadUserProfile}
        defaultProxy={currentUser?.proxy_url}
      />
    </div>
  );
};
