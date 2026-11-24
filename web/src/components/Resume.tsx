import React, { useEffect, useState } from "react";
import { Check, Info, Save } from "lucide-react";
import { fetchResume, updateResume } from "../api";

export const Resume: React.FC = () => {
  const [text, setText] = useState("");
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedSuccess, setSavedSuccess] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const data = await fetchResume();
        setText(data.text);
        setUpdatedAt(data.updated_at);
      } catch (err) {
        console.error(err);
      }
    })();
  }, []);

  const handleSave = async () => {
    try {
      setSaving(true);
      await updateResume(text);
      setSavedSuccess(true);
      setUpdatedAt(new Date().toISOString());
      setTimeout(() => setSavedSuccess(false), 3000);
    } catch (err) {
      console.error(err);
      alert("Не удалось сохранить резюме");
    } finally {
      setSaving(false);
    }
  };

  const wordCount = text.trim() ? text.trim().split(/\s+/).length : 0;
  const charCount = text.length;

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Резюме кандидата</h1>
          <p className="text-sm text-slate-400">
            Этот текст используется нейросетью (GigaChat / DeepSeek) для генерации персонализированных сопроводительных писем
          </p>
        </div>

        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold rounded-lg shadow transition-colors disabled:opacity-50"
        >
          {savedSuccess ? (
            <>
              <Check className="w-4 h-4 mr-1.5 text-emerald-300" />
              Сохранено!
            </>
          ) : (
            <>
              <Save className="w-4 h-4 mr-1.5" />
              {saving ? "Сохранение..." : "Сохранить резюме"}
            </>
          )}
        </button>
      </div>

      {/* Advice banner */}
      <div className="bg-blue-950/40 border border-blue-800/60 rounded-xl p-4 flex items-start space-x-3 text-xs text-blue-300">
        <Info className="w-5 h-5 flex-shrink-0 text-blue-400 mt-0.5" />
        <div className="space-y-1">
          <p className="font-semibold text-blue-200">Совет по заполнению:</p>
          <p>
            Укажите стек технологий, ключевые проекты, реализованные задачи и достижения с цифрами.
            Чем подробнее описан стек и опыт, тем более убедительными и релевантными получатся письма для каждой вакансии.
          </p>
        </div>
      </div>

      {/* Editor Box */}
      <div className="bg-slate-800/80 border border-slate-700 rounded-xl p-5 shadow space-y-3">
        <div className="flex items-center justify-between text-xs text-slate-400">
          <span>Редактор резюме (текстовый формат)</span>
          <div className="space-x-3">
            <span>Слов: <strong className="text-slate-200">{wordCount}</strong></span>
            <span>Символов: <strong className="text-slate-200">{charCount}</strong></span>
          </div>
        </div>

        <textarea
          rows={18}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={`Пример:
Опыт работы: 6+ лет Backend разработки (Python, FastAPI, Django, PostgreSQL, Docker, Kubernetes).
Ключевые проекты:
- Разработка high-load микросервисов обработки платежей (15k RPS).
- Оптимизация тяжелых SQL-запросов и переход на партиционированные таблицы в PostgreSQL.
- Настройка CI/CD пайплайнов на GitLab CI и развертывание в Kubernetes...`}
          className="w-full bg-slate-900 border border-slate-700 rounded-xl p-4 text-slate-200 text-sm leading-relaxed focus:outline-none focus:border-blue-500 font-mono resize-y"
        />

        {updatedAt && (
          <p className="text-[11px] text-slate-500 text-right">
            Последнее сохранение: {new Date(updatedAt).toLocaleString("ru-RU")}
          </p>
        )}
      </div>
    </div>
  );
};
