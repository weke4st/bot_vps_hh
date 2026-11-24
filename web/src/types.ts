export type Period = "7d" | "30d" | "all";

export interface DailyStatPoint {
  date: string;
  applications: number;
  responses: number;
  interviews: number;
}

export interface CompanyStatPoint {
  company: string;
  count: number;
}

export interface StatsSummary {
  period: string;
  total_applications: number;
  today_applications: number;
  total_responses: number;
  total_interviews: number;
  response_rate_pct: number;
  interview_rate_pct: number;
  timeline: DailyStatPoint[];
  status_distribution: Record<string, number>;
  top_companies: CompanyStatPoint[];
}

export interface VacancySummary {
  id: number;
  hh_id: string;
  title: string;
  company: string;
  salary?: string | null;
  url: string;
  status: string;
  description?: string | null;
}

export interface ApplicationListItem {
  id: number;
  vacancy_id: number;
  vacancy: VacancySummary | null;
  status: string;
  cover_letter_preview?: string | null;
  sent_at?: string | null;
  response_at?: string | null;
  response_type?: string | null;
  created_at: string;
}

export interface ApplicationPagination {
  items: ApplicationListItem[];
  total: number;
  page: number;
  limit: number;
  pages: number;
}

export interface CaptchaAttemptItem {
  id: number;
  image_path: string;
  model_answer?: string | null;
  correct?: boolean | null;
  created_at: string;
}

export interface LLMCallItem {
  id: number;
  provider: string;
  model: string;
  prompt_tokens: number;
  completion_tokens: number;
  latency_ms: number;
  created_at: string;
}

export interface ApplicationDetail {
  id: number;
  vacancy: VacancySummary;
  cover_letter?: string | null;
  status: string;
  sent_at?: string | null;
  response_at?: string | null;
  response_type?: string | null;
  created_at: string;
  captcha_attempts: CaptchaAttemptItem[];
  llm_calls: LLMCallItem[];
}

export interface SettingsData {
  max_applications_per_hour: number;
  max_applications_per_day: number;
  min_delay_between_applies_sec: number;
  max_delay_between_applies_sec: number;
  search_interval_minutes: number;

  search_query: string;
  search_region: number;
  salary_from?: number | null;
  experience?: string | null;
  work_format?: string | null;
  target_salary?: string;

  llm_provider: "gigachat" | "deepseek";
  gigachat_auth_key_masked: string;
  gigachat_scope: string;
  gigachat_model: string;
  deepseek_api_key_masked: string;
  deepseek_model: string;
  llm_temperature: number;
  llm_max_tokens: number;

  ocr_endpoint: string;
  ocr_model: string;
  ocr_max_retries: number;
}

export interface BotStatus {
  status: "idle" | "running" | "paused" | "stopped" | "error";
  is_running: boolean;
  current_action?: string | null;
  current_vacancy?: string | null;
  uptime_seconds: number;
  last_run?: string | null;
  next_run?: string | null;
  applications_today: number;
  applications_this_hour: number;
  limits: {
    per_hour?: number;
    per_day?: number;
    min_delay_sec?: number;
    interval_min?: number;
  };
  error_message?: string | null;
}

export interface UserProfile {
  id: number;
  email: string;
  full_name: string;
  hh_phone?: string | null;
  hh_is_connected: boolean;
  selected_resume_id?: string | null;
  selected_resume_title?: string | null;
  bot_enabled: boolean;
  bot_status: string;
  current_action: string;
  search_query: string;
  search_region: number;
  target_salary: string;
  proxy_url?: string | null;
  gigachat_auth_key_masked: string;
  last_run_at?: string | null;
  created_at: string;
}

export interface ResumeOption {
  id: string;
  title: string;
}

export interface LogEntry {
  timestamp: string;
  level: string;
  message: string;
  logger: string;
}
