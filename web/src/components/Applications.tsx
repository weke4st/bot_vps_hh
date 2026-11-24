import React, { useEffect, useState } from "react";
import {
  AlertTriangle,
  Building2,
  ExternalLink,
  Eye,
  RotateCcw,
  Search,
  X,
  Zap,
} from "lucide-react";
import { fetchApplicationDetail, fetchApplications, retryApplication } from "../api";
import { ApplicationDetail, ApplicationPagination } from "../types";

const STATUS_BADGES: Record<
  string,
  { label: string; bg: string; text: string; border: string }
> = {
  pending: { label: "В очереди", bg: "bg-slate-800", text: "text-slate-300", border: "border-slate-700" },
  sent: { label: "Отправлен", bg: "bg-blue-900/40", text: "text-blue-300", border: "border-blue-700/50" },
  response: { label: "Ответ", bg: "bg-emerald-900/40", text: "text-emerald-300", border: "border-emerald-700/50" },
  interview: { label: "Интервью", bg: "bg-purple-900/40", text: "text-purple-300", border: "border-purple-700/50" },
  rejected: { label: "Отказ", bg: "bg-rose-900/40", text: "text-rose-300", border: "border-rose-700/50" },
  manual: { label: "Вручную", bg: "bg-amber-900/40", text: "text-amber-300", border: "border-amber-700/50" },
};

export const Applications: React.FC = () => {
  const [data, setData] = useState<ApplicationPagination | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [searchQuery, setSearchQuery] = useState("");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [selectedApp, setSelectedApp] = useState<ApplicationDetail | null>(null);
  const [retryingId, setRetryingId] = useState<number | null>(null);

  const loadList = async () => {
    try {
      setLoading(true);
      const res = await fetchApplications(statusFilter, page, 20);
      setData(res);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadList();
  }, [statusFilter, page]);

  const handleOpenDetail = async (id: number) => {
    try {
      const detail = await fetchApplicationDetail(id);
      setSelectedApp(detail);
    } catch (err) {
      console.error(err);
    }
  };

  const handleRetry = async (id: number) => {
    try {
      setRetryingId(id);
      await retryApplication(id);
      await loadList();
      if (selectedApp?.id === id) {
        const updated = await fetchApplicationDetail(id);
        setSelectedApp(updated);
      }
    } catch (err) {
      console.error(err);
      alert("Не удалось сбросить статус отклика");
    } finally {
      setRetryingId(null);
    }
  };

  const filteredItems = (data?.items || []).filter((item) => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    const title = item.vacancy?.title?.toLowerCase() || "";
    const company = item.vacancy?.company?.toLowerCase() || "";
    return title.includes(q) || company.includes(q);
  });

  return (
    <div className="space-y-6">
      {/* Header & Filter Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Отклики на вакансии</h1>
          <p className="text-sm text-slate-400">
            История отправленных заявок, сгенерированные письма и статус ответов
          </p>
        </div>

        {/* Search Input */}
        <div className="relative w-full sm:w-72">
          <Search className="w-4 h-4 absolute left-3 top-3 text-slate-400" />
          <input
            type="text"
            placeholder="Поиск по названию или компании..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-slate-800 border border-slate-700 rounded-lg pl-9 pr-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500"
          />
        </div>
      </div>

      {/* Status Filter Pills */}
      <div className="flex flex-wrap gap-2">
        {[
          { id: "", label: "Все отклики" },
          { id: "sent", label: "Отправлены" },
          { id: "response", label: "Ответы" },
          { id: "interview", label: "Интервью" },
          { id: "manual", label: "Требуют внимания" },
          { id: "rejected", label: "Отказы" },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => {
              setStatusFilter(tab.id);
              setPage(1);
            }}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
              statusFilter === tab.id
                ? "bg-blue-600 text-white border-blue-500"
                : "bg-slate-800 text-slate-400 border-slate-700 hover:text-white"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Table Container */}
      <div className="bg-slate-800/80 border border-slate-700 rounded-xl overflow-hidden shadow">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm text-slate-300">
            <thead className="bg-slate-900/60 text-xs uppercase text-slate-400 border-b border-slate-700">
              <tr>
                <th className="px-5 py-3.5">Вакансия</th>
                <th className="px-5 py-3.5">Компания</th>
                <th className="px-5 py-3.5">Зарплата</th>
                <th className="px-5 py-3.5">Статус</th>
                <th className="px-5 py-3.5">Дата отправки</th>
                <th className="px-5 py-3.5 text-right">Действия</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700/60">
              {filteredItems.length > 0 ? (
                filteredItems.map((app) => {
                  const badge = STATUS_BADGES[app.status] || STATUS_BADGES.pending;
                  return (
                    <tr key={app.id} className="hover:bg-slate-750/50 transition-colors">
                      <td className="px-5 py-4 font-medium text-white max-w-xs truncate">
                        <div className="flex items-center space-x-2">
                          <span className="truncate">{app.vacancy?.title || "Без названия"}</span>
                          {app.vacancy?.url && (
                            <a
                              href={app.vacancy.url}
                              target="_blank"
                              rel="noreferrer"
                              className="text-slate-500 hover:text-blue-400"
                            >
                              <ExternalLink className="w-3.5 h-3.5" />
                            </a>
                          )}
                        </div>
                      </td>
                      <td className="px-5 py-4 text-slate-400">{app.vacancy?.company || "—"}</td>
                      <td className="px-5 py-4 text-slate-300">{app.vacancy?.salary || "Не указана"}</td>
                      <td className="px-5 py-4">
                        <span
                          className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${badge.bg} ${badge.text} ${badge.border}`}
                        >
                          {badge.label}
                        </span>
                      </td>
                      <td className="px-5 py-4 text-slate-400 text-xs">
                        {app.sent_at
                          ? new Date(app.sent_at).toLocaleString("ru-RU", {
                              day: "2-digit",
                              month: "short",
                              hour: "2-digit",
                              minute: "2-digit",
                            })
                          : "Ожидает"}
                      </td>
                      <td className="px-5 py-4 text-right space-x-2">
                        <button
                          onClick={() => handleOpenDetail(app.id)}
                          className="inline-flex items-center px-2.5 py-1 text-xs font-medium bg-slate-700 hover:bg-slate-600 text-slate-200 rounded-md transition-colors"
                        >
                          <Eye className="w-3.5 h-3.5 mr-1" />
                          Письмо
                        </button>
                        {app.status === "manual" && (
                          <button
                            onClick={() => handleRetry(app.id)}
                            disabled={retryingId === app.id}
                            className="inline-flex items-center px-2.5 py-1 text-xs font-medium bg-amber-600/30 hover:bg-amber-600/50 text-amber-300 border border-amber-600/50 rounded-md transition-colors"
                          >
                            <RotateCcw
                              className={`w-3.5 h-3.5 mr-1 ${
                                retryingId === app.id ? "animate-spin" : ""
                              }`}
                            />
                            Повторить
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td colSpan={6} className="px-5 py-8 text-center text-slate-500 text-sm">
                    {loading ? "Загрузка..." : "Откликов по заданным фильтрам не найдено"}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination Controls */}
        {data && data.pages > 1 && (
          <div className="px-5 py-3 bg-slate-900/60 border-t border-slate-700 flex items-center justify-between text-xs text-slate-400">
            <span>
              Страница {data.page} из {data.pages} (всего {data.total} записей)
            </span>
            <div className="space-x-1">
              <button
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                className="px-3 py-1 bg-slate-800 border border-slate-700 rounded hover:bg-slate-700 disabled:opacity-40"
              >
                Назад
              </button>
              <button
                disabled={page >= data.pages}
                onClick={() => setPage((p) => p + 1)}
                className="px-3 py-1 bg-slate-800 border border-slate-700 rounded hover:bg-slate-700 disabled:opacity-40"
              >
                Вперед
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Application Detail Modal */}
      {selectedApp && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto shadow-2xl flex flex-col">
            {/* Modal Header */}
            <div className="p-5 border-b border-slate-800 flex items-start justify-between">
              <div>
                <h2 className="text-lg font-bold text-white">
                  {selectedApp.vacancy.title}
                </h2>
                <div className="flex items-center space-x-3 mt-1 text-xs text-slate-400">
                  <span className="flex items-center">
                    <Building2 className="w-3.5 h-3.5 mr-1" />
                    {selectedApp.vacancy.company}
                  </span>
                  <span>{selectedApp.vacancy.salary || "Зарплата не указана"}</span>
                  <a
                    href={selectedApp.vacancy.url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-blue-400 hover:underline flex items-center"
                  >
                    Открыть на hh.ru
                    <ExternalLink className="w-3 h-3 ml-1" />
                  </a>
                </div>
              </div>
              <button
                onClick={() => setSelectedApp(null)}
                className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Content */}
            <div className="p-5 space-y-5 overflow-y-auto text-sm">
              {/* Cover Letter Box */}
              <div>
                <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
                  Сопроводительное письмо (сгенерировано LLM)
                </label>
                <div className="bg-slate-950/80 border border-slate-800 rounded-xl p-4 text-slate-200 whitespace-pre-wrap leading-relaxed font-sans text-sm">
                  {selectedApp.cover_letter || "Письмо отсутствует"}
                </div>
              </div>

              {/* LLM & OCR Logs */}
              {selectedApp.llm_calls.length > 0 && (
                <div className="bg-slate-800/40 border border-slate-800 rounded-xl p-3.5 text-xs">
                  <div className="flex items-center text-slate-300 font-semibold mb-2">
                    <Zap className="w-3.5 h-3.5 mr-1 text-amber-400" />
                    Параметры генерации LLM
                  </div>
                  {selectedApp.llm_calls.map((c) => (
                    <div key={c.id} className="text-slate-400 flex justify-between py-0.5">
                      <span>Провайдер: {c.provider} ({c.model})</span>
                      <span>Токены: {c.prompt_tokens + c.completion_tokens} | {c.latency_ms} мс</span>
                    </div>
                  ))}
                </div>
              )}

              {selectedApp.captcha_attempts.length > 0 && (
                <div className="bg-slate-800/40 border border-slate-800 rounded-xl p-3.5 text-xs">
                  <div className="flex items-center text-slate-300 font-semibold mb-2">
                    <AlertTriangle className="w-3.5 h-3.5 mr-1 text-blue-400" />
                    Попытки решения CAPTCHA ({selectedApp.captcha_attempts.length})
                  </div>
                  {selectedApp.captcha_attempts.map((att, idx) => (
                    <div key={att.id} className="text-slate-400 flex justify-between py-0.5">
                      <span>Попытка #{idx + 1}: ответ «{att.model_answer || "—"}»</span>
                      <span className="text-slate-500 font-mono text-[10px]">{att.image_path}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="p-4 border-t border-slate-800 bg-slate-900 flex justify-end space-x-3">
              <button
                onClick={() => setSelectedApp(null)}
                className="px-4 py-2 text-xs font-medium rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300"
              >
                Закрыть
              </button>
              {selectedApp.status === "manual" && (
                <button
                  onClick={() => handleRetry(selectedApp.id)}
                  disabled={retryingId === selectedApp.id}
                  className="px-4 py-2 text-xs font-semibold rounded-lg bg-blue-600 hover:bg-blue-500 text-white flex items-center"
                >
                  <RotateCcw className="w-3.5 h-3.5 mr-1" />
                  Повторить отклик
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
