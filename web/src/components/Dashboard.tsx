import React, { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  ArrowUpRight,
  Briefcase,
  CheckCircle2,
  Clock,
  Send,
  Users,
} from "lucide-react";
import { fetchStats } from "../api";
import { Period, StatsSummary } from "../types";

const STATUS_COLORS: Record<string, string> = {
  pending: "#64748b",
  sent: "#3b82f6",
  response: "#10b981",
  interview: "#8b5cf6",
  rejected: "#ef4444",
  manual: "#f59e0b",
};

export const Dashboard: React.FC = () => {
  const [period, setPeriod] = useState<Period>("7d");
  const [stats, setStats] = useState<StatsSummary | null>(null);

  const loadData = async () => {
    try {
      const data = await fetchStats(period);
      setStats(data);
    } catch (err) {
      console.error("Failed to load dashboard stats", err);
    }
  };

  useEffect(() => {
    loadData();
  }, [period]);

  const pieData = stats
    ? Object.entries(stats.status_distribution).map(([status, count]) => ({
        name: status,
        value: count,
      }))
    : [];

  return (
    <div className="space-y-6">
      {/* Top Filter Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Аналитика откликов</h1>
          <p className="text-sm text-slate-400">
            Статистика конверсии, активности и статусов откликов
          </p>
        </div>

        <div className="flex bg-slate-800 p-1 rounded-lg border border-slate-700 w-fit">
          {(["7d", "30d", "all"] as Period[]).map((p) => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-all ${
                period === p
                  ? "bg-blue-600 text-white shadow"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              {p === "7d" ? "7 дней" : p === "30d" ? "30 дней" : "Все время"}
            </button>
          ))}
        </div>
      </div>

      {/* KPI Stat Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-slate-800/80 border border-slate-700 rounded-xl p-5 shadow">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
              Сегодня
            </span>
            <div className="p-2 bg-blue-500/10 text-blue-400 rounded-lg">
              <Clock className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3 flex items-baseline justify-between">
            <span className="text-3xl font-bold text-white">
              {stats?.today_applications ?? 0}
            </span>
            <span className="text-xs text-slate-400">откликов</span>
          </div>
        </div>

        <div className="bg-slate-800/80 border border-slate-700 rounded-xl p-5 shadow">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
              Всего за период
            </span>
            <div className="p-2 bg-emerald-500/10 text-emerald-400 rounded-lg">
              <Send className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3 flex items-baseline justify-between">
            <span className="text-3xl font-bold text-white">
              {stats?.total_applications ?? 0}
            </span>
            <span className="text-xs text-emerald-400 flex items-center">
              <ArrowUpRight className="w-3.5 h-3.5 mr-0.5" />
              активно
            </span>
          </div>
        </div>

        <div className="bg-slate-800/80 border border-slate-700 rounded-xl p-5 shadow">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
              Конверсия в ответы
            </span>
            <div className="p-2 bg-purple-500/10 text-purple-400 rounded-lg">
              <Users className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3 flex items-baseline justify-between">
            <span className="text-3xl font-bold text-white">
              {stats?.response_rate_pct ?? 0}%
            </span>
            <span className="text-xs text-slate-400">
              {stats?.total_responses ?? 0} ответов
            </span>
          </div>
        </div>

        <div className="bg-slate-800/80 border border-slate-700 rounded-xl p-5 shadow">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
              Интервью / Приглашения
            </span>
            <div className="p-2 bg-amber-500/10 text-amber-400 rounded-lg">
              <CheckCircle2 className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3 flex items-baseline justify-between">
            <span className="text-3xl font-bold text-white">
              {stats?.interview_rate_pct ?? 0}%
            </span>
            <span className="text-xs text-slate-400">
              {stats?.total_interviews ?? 0} собеседований
            </span>
          </div>
        </div>
      </div>

      {/* Main Charts Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Line chart: Applications timeline */}
        <div className="lg:col-span-2 bg-slate-800/80 border border-slate-700 rounded-xl p-5">
          <h2 className="text-base font-semibold text-white mb-4">
            Динамика откликов по дням
          </h2>
          <div className="h-72 w-full">
            {stats && stats.timeline.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={stats.timeline}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                  <XAxis dataKey="date" stroke="#94a3b8" fontSize={12} />
                  <YAxis stroke="#94a3b8" fontSize={12} allowDecimals={false} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "#1e293b",
                      border: "1px solid #475569",
                      borderRadius: "8px",
                      color: "#fff",
                    }}
                  />
                  <Legend />
                  <Line
                    type="monotone"
                    dataKey="applications"
                    name="Отклики"
                    stroke="#3b82f6"
                    strokeWidth={2.5}
                    dot={{ fill: "#3b82f6", r: 4 }}
                  />
                  <Line
                    type="monotone"
                    dataKey="responses"
                    name="Ответы"
                    stroke="#10b981"
                    strokeWidth={2}
                  />
                  <Line
                    type="monotone"
                    dataKey="interviews"
                    name="Интервью"
                    stroke="#8b5cf6"
                    strokeWidth={2}
                  />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex h-full items-center justify-center text-slate-500 text-sm">
                Нет данных за выбранный период
              </div>
            )}
          </div>
        </div>

        {/* Status Distribution (Pie) */}
        <div className="bg-slate-800/80 border border-slate-700 rounded-xl p-5">
          <h2 className="text-base font-semibold text-white mb-4">
            Распределение статусов
          </h2>
          <div className="h-72 w-full">
            {pieData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={pieData}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    outerRadius={80}
                    innerRadius={45}
                    paddingAngle={3}
                  >
                    {pieData.map((entry) => (
                      <Cell
                        key={`cell-${entry.name}`}
                        fill={STATUS_COLORS[entry.name] || "#64748b"}
                      />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "#1e293b",
                      border: "1px solid #475569",
                      borderRadius: "8px",
                    }}
                  />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex h-full items-center justify-center text-slate-500 text-sm">
                Нет данных
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Top 10 Companies Bar Chart */}
      <div className="bg-slate-800/80 border border-slate-700 rounded-xl p-5">
        <div className="flex items-center space-x-2 mb-4">
          <Briefcase className="w-5 h-5 text-blue-400" />
          <h2 className="text-base font-semibold text-white">
            Топ-10 компаний по количеству откликов
          </h2>
        </div>
        <div className="h-64 w-full">
          {stats && stats.top_companies.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={stats.top_companies}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="company" stroke="#94a3b8" fontSize={11} />
                <YAxis stroke="#94a3b8" fontSize={12} allowDecimals={false} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#1e293b",
                    border: "1px solid #475569",
                    borderRadius: "8px",
                  }}
                />
                <Bar dataKey="count" name="Откликов" fill="#3b82f6" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex h-full items-center justify-center text-slate-500 text-sm">
              Пока нет отправленных откликов в компании
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
