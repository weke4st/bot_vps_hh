import React, { useEffect, useRef, useState } from "react";
import {
  Copy,
  Trash2,
} from "lucide-react";
import { LogEntry } from "../types";

interface LogsProps {
  logs: LogEntry[];
  onClearLogs: () => void;
  connected: boolean;
}

export const Logs: React.FC<LogsProps> = ({ logs, onClearLogs, connected }) => {
  const [levelFilter, setLevelFilter] = useState<string>("");
  const [autoScroll, setAutoScroll] = useState<boolean>(true);
  const terminalEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (autoScroll && terminalEndRef.current) {
      terminalEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs, autoScroll]);

  const filteredLogs = logs.filter((l) => {
    if (!levelFilter) return true;
    return l.level.toUpperCase() === levelFilter.toUpperCase();
  });

  const getLevelBadge = (level: string) => {
    const lvl = level.toUpperCase();
    if (lvl === "ERROR" || lvl === "CRITICAL") {
      return <span className="text-rose-400 font-bold">ERR</span>;
    }
    if (lvl === "WARNING" || lvl === "WARN") {
      return <span className="text-amber-400 font-bold">WRN</span>;
    }
    return <span className="text-blue-400">INF</span>;
  };

  const handleCopyAll = () => {
    const text = filteredLogs
      .map((l) => `[${l.timestamp}] [${l.level}] ${l.message}`)
      .join("\n");
    navigator.clipboard.writeText(text);
  };

  return (
    <div className="space-y-4">
      {/* Header & Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Терминал событий (Live)</h1>
          <p className="text-sm text-slate-400">
            Прямая трансляция логов браузера, решателя капчи и откликов по WebSocket
          </p>
        </div>

        <div className="flex items-center space-x-2">
          {/* Connection status indicator */}
          <div className="flex items-center px-2.5 py-1 rounded bg-slate-800 border border-slate-700 text-xs">
            <span
              className={`w-2 h-2 rounded-full mr-2 ${
                connected ? "bg-emerald-400" : "bg-rose-400 animate-pulse"
              }`}
            />
            <span className="text-slate-300">
              {connected ? "WebSocket онлайн" : "Подключение..."}
            </span>
          </div>

          <button
            onClick={handleCopyAll}
            className="p-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg border border-slate-700 text-xs flex items-center"
            title="Скопировать все логи"
          >
            <Copy className="w-3.5 h-3.5" />
          </button>

          <button
            onClick={onClearLogs}
            className="p-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg border border-slate-700 text-xs flex items-center"
            title="Очистить терминал"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Filter and settings bar */}
      <div className="flex items-center justify-between bg-slate-800/80 border border-slate-700 rounded-lg px-4 py-2 text-xs">
        <div className="flex items-center space-x-2">
          <span className="text-slate-400">Уровень:</span>
          {["", "INFO", "WARNING", "ERROR"].map((lvl) => (
            <button
              key={lvl}
              onClick={() => setLevelFilter(lvl)}
              className={`px-2 py-1 rounded font-medium transition-colors ${
                levelFilter === lvl
                  ? "bg-blue-600 text-white"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              {lvl || "Все"}
            </button>
          ))}
        </div>

        <label className="flex items-center space-x-1.5 text-slate-400 cursor-pointer">
          <input
            type="checkbox"
            checked={autoScroll}
            onChange={(e) => setAutoScroll(e.target.checked)}
            className="rounded bg-slate-900 border-slate-700 text-blue-600 focus:ring-0"
          />
          <span>Автоскролл</span>
        </label>
      </div>

      {/* Terminal Output */}
      <div className="bg-slate-950 border border-slate-800 rounded-xl p-4 font-mono text-xs text-slate-300 h-[600px] overflow-y-auto space-y-1 shadow-inner">
        {filteredLogs.length > 0 ? (
          filteredLogs.map((log, index) => (
            <div
              key={index}
              className="flex items-start space-x-2 py-0.5 hover:bg-slate-900/60 rounded px-1"
            >
              <span className="text-slate-600 whitespace-nowrap">
                {new Date(log.timestamp).toLocaleTimeString()}
              </span>
              <span className="whitespace-nowrap">{getLevelBadge(log.level)}</span>
              <span className="text-slate-500 whitespace-nowrap">
                [{log.logger || "app"}]
              </span>
              <span className="text-slate-200 break-all">{log.message}</span>
            </div>
          ))
        ) : (
          <div className="flex h-full items-center justify-center text-slate-600 text-sm">
            Логи отсутствуют или ожидают событий...
          </div>
        )}
        <div ref={terminalEndRef} />
      </div>
    </div>
  );
};
