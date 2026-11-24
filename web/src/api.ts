import {
  ApplicationDetail,
  ApplicationPagination,
  BotStatus,
  LogEntry,
  Period,
  SettingsData,
  StatsSummary,
} from "./types";

const API_BASE = "/api";

function getHeaders(): HeadersInit {
  const token = localStorage.getItem("hh_bot_token") || "";
  const headers: HeadersInit = {
    "Content-Type": "application/json",
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  return headers;
}

// ═══════════════════════════════════════════════════════════════════════════
// SaaS Authentication & User Profile
// ═══════════════════════════════════════════════════════════════════════════

export async function loginUser(email: string, password: string): Promise<{ access_token: string; user: any }> {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Неверный логин или пароль");
  }
  const data = await res.json();
  localStorage.setItem("hh_bot_token", data.access_token);
  return data;
}

export async function registerUser(email: string, password: string, full_name = ""): Promise<{ access_token: string; user: any }> {
  const res = await fetch(`${API_BASE}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, full_name }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Ошибка регистрации");
  }
  const data = await res.json();
  localStorage.setItem("hh_bot_token", data.access_token);
  return data;
}

export async function fetchCurrentUser(): Promise<any> {
  const res = await fetch(`${API_BASE}/auth/me`, {
    headers: getHeaders(),
  });
  if (!res.ok) throw new Error("Требуется авторизация");
  return res.json();
}

export async function logoutUser(): Promise<void> {
  await fetch(`${API_BASE}/auth/logout`, {
    method: "POST",
    headers: getHeaders(),
  }).catch(() => {});
  localStorage.removeItem("hh_bot_token");
}

// ═══════════════════════════════════════════════════════════════════════════
// HH.ru Web Login Wizard
// ═══════════════════════════════════════════════════════════════════════════

export async function startHHLogin(phone: string, proxy_url?: string): Promise<{ status: string; message: string }> {
  const res = await fetch(`${API_BASE}/hh/login/start`, {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify({ phone, proxy_url }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Ошибка отправки СМС");
  }
  return res.json();
}

export async function verifyHHCode(code: string): Promise<{ status: string; message: string; resumes: any[] }> {
  const res = await fetch(`${API_BASE}/hh/login/verify`, {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify({ code }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Ошибка проверки кода");
  }
  return res.json();
}

export async function cancelHHLogin(): Promise<void> {
  await fetch(`${API_BASE}/hh/login/cancel`, {
    method: "POST",
    headers: getHeaders(),
  }).catch(() => {});
}

export async function updateUserSettings(data: any): Promise<any> {
  const res = await fetch(`${API_BASE}/user/settings`, {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Ошибка сохранения настроек");
  }
  return res.json();
}

export async function toggleUserBot(): Promise<{ success: boolean; message: string }> {
  const res = await fetch(`${API_BASE}/user/bot/toggle`, {
    method: "POST",
    headers: getHeaders(),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Ошибка запуска бота");
  }
  return res.json();
}

export async function resetUserVacancies(): Promise<{ success: boolean; message: string }> {
  const res = await fetch(`${API_BASE}/user/vacancies/reset`, {
    method: "POST",
    headers: getHeaders(),
  });
  if (!res.ok) throw new Error("Ошибка сброса вакансий");
  return res.json();
}

export async function fetchStats(period: Period = "7d"): Promise<StatsSummary> {
  const res = await fetch(`${API_BASE}/stats?period=${period}`, {
    headers: getHeaders(),
  });
  if (!res.ok) throw new Error("Failed to load statistics");
  return res.json();
}

export async function fetchApplications(
  status = "",
  page = 1,
  limit = 20
): Promise<ApplicationPagination> {
  const params = new URLSearchParams({
    page: String(page),
    limit: String(limit),
  });
  if (status) params.append("status", status);

  const res = await fetch(`${API_BASE}/applications?${params.toString()}`, {
    headers: getHeaders(),
  });
  if (!res.ok) throw new Error("Failed to load applications");
  return res.json();
}

export async function fetchApplicationDetail(id: number): Promise<ApplicationDetail> {
  const res = await fetch(`${API_BASE}/applications/${id}`, {
    headers: getHeaders(),
  });
  if (!res.ok) throw new Error(`Failed to load application #${id}`);
  return res.json();
}

export async function retryApplication(id: number): Promise<{ success: boolean; message: string }> {
  const res = await fetch(`${API_BASE}/applications/${id}/retry`, {
    method: "POST",
    headers: getHeaders(),
  });
  if (!res.ok) throw new Error(`Failed to retry application #${id}`);
  return res.json();
}

export async function fetchSettings(): Promise<SettingsData> {
  const res = await fetch(`${API_BASE}/settings`, {
    headers: getHeaders(),
  });
  if (!res.ok) throw new Error("Failed to load settings");
  return res.json();
}

export async function updateSettings(data: Partial<SettingsData>): Promise<SettingsData> {
  const res = await fetch(`${API_BASE}/settings`, {
    method: "PUT",
    headers: getHeaders(),
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to update settings");
  return res.json();
}

export async function fetchResume(): Promise<{ text: string; updated_at: string | null }> {
  const res = await fetch(`${API_BASE}/resume`, {
    headers: getHeaders(),
  });
  if (!res.ok) throw new Error("Failed to load resume");
  return res.json();
}

export async function updateResume(text: string): Promise<void> {
  const res = await fetch(`${API_BASE}/resume`, {
    method: "PUT",
    headers: getHeaders(),
    body: JSON.stringify({ text }),
  });
  if (!res.ok) throw new Error("Failed to save resume");
}

export async function fetchBotStatus(): Promise<BotStatus> {
  const res = await fetch(`${API_BASE}/bot/status`, {
    headers: getHeaders(),
  });
  if (!res.ok) throw new Error("Failed to load bot status");
  return res.json();
}

export async function startBot(): Promise<void> {
  const res = await fetch(`${API_BASE}/bot/start`, {
    method: "POST",
    headers: getHeaders(),
  });
  if (!res.ok) throw new Error("Failed to start bot");
}

export async function stopBot(): Promise<void> {
  const res = await fetch(`${API_BASE}/bot/stop`, {
    method: "POST",
    headers: getHeaders(),
  });
  if (!res.ok) throw new Error("Failed to stop bot");
}

export async function fetchLogs(limit = 100): Promise<{ logs: LogEntry[]; total: number }> {
  const res = await fetch(`${API_BASE}/logs?limit=${limit}`, {
    headers: getHeaders(),
  });
  if (!res.ok) throw new Error("Failed to fetch logs");
  return res.json();
}
