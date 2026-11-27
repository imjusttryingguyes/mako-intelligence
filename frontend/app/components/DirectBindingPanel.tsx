"use client";

import { useEffect, useState, type FormEvent } from "react";

type Binding = {
  provider: "yandex_direct";
  client_login: string | null;
  status: "not_configured" | "configured_unverified";
};

type Props = {
  organizationId: string;
  projectId: string;
  archived: boolean;
  onChanged: () => void;
};

const api = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function DirectBindingPanel({
  organizationId, projectId, archived, onChanged,
}: Props) {
  const [expanded, setExpanded] = useState(false);
  const [binding, setBinding] = useState<Binding | null>(null);
  const [login, setLogin] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [confirmUnlink, setConfirmUnlink] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const url = `${api}/organizations/${organizationId}/projects/${projectId}/direct-binding`;

  useEffect(() => {
    if (!expanded) return;
    let cancelled = false;
    setLoading(true);
    setError("");
    setNotice("");
    void fetch(url, { credentials: "include", cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) throw new Error("Direct configuration unavailable");
        return (await response.json()) as Binding;
      })
      .then((data) => {
        if (cancelled) return;
        setBinding(data);
        setLogin(data.client_login ?? "");
      })
      .catch(() => {
        if (!cancelled) setError("Не удалось загрузить настройки Директа.");
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [expanded, url]);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (archived) return;
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const response = await fetch(url, {
        method: "PUT",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ client_login: login.trim() }),
      });
      if (response.status === 422) {
        setError("Укажи логин Директа латиницей, без пробелов (до 255 символов).");
        return;
      }
      if (response.status === 409) {
        setError("Архивный проект нельзя изменять.");
        return;
      }
      if (response.status === 401 || response.status === 403 || response.status === 404) {
        setError("Нет доступа к сохранению настройки. Возможно, сессия истекла.");
        return;
      }
      if (!response.ok) throw new Error("Binding failed");
      const data = (await response.json()) as Binding;
      setBinding(data);
      setLogin(data.client_login ?? "");
      setNotice("Логин сохранён. OAuth-доступ пока НЕ подключён и не проверен.");
      onChanged();
    } catch {
      setError("Не удалось сохранить привязку. Проверь backend.");
    } finally {
      setSaving(false);
    }
  }

  async function unlink() {
    if (archived) return;
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const response = await fetch(url, { method: "DELETE", credentials: "include" });
      if (!response.ok) {
        if (response.status === 409) {
          setError("Архивный проект нельзя изменять.");
          return;
        }
        if (response.status === 401 || response.status === 403 || response.status === 404) {
          setError("Нет доступа к отвязке или привязка уже отсутствует.");
          return;
        }
        throw new Error("Unlink failed");
      }
      setBinding({
        provider: "yandex_direct", client_login: null, status: "not_configured",
      });
      setLogin("");
      setConfirmUnlink(false);
      setNotice("Привязка удалена. История изменений сохранена.");
      onChanged();
    } catch {
      setError("Не удалось убрать привязку. Проверь backend.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="direct-settings">
      <button
        type="button"
        className="project-settings-link"
        onClick={() => {
          setExpanded((value) => !value);
          setConfirmUnlink(false);
        }}
      >
        {expanded ? "Скрыть настройки Директа" : "Настроить Яндекс Директ"}
      </button>
      {expanded && (
        <div className="direct-panel">
          <div className="eyebrow">ЯНДЕКС ДИРЕКТ · C2.2a</div>
          {loading && <p className="muted">Загружаем настройки…</p>}
          {!loading && binding && (
            <>
              <p className="direct-status">
                {binding.status === "configured_unverified"
                  ? "Логин указан · подключение не подтверждено"
                  : "Аккаунт не указан"}
              </p>
              <p className="direct-disclaimer">
                Это только привязка логина к проекту. OAuth-токен не сохраняется,
                рекламные данные не загружаются.
              </p>
              {archived ? (
                <p className="muted">Проект в архиве — настройки доступны только для просмотра.</p>
              ) : (
                <form onSubmit={(event) => void save(event)}>
                  <label className="field-label" htmlFor={`direct-login-${projectId}`}>
                    Логин рекламодателя
                  </label>
                  <input
                    className="form-input"
                    id={`direct-login-${projectId}`}
                    value={login}
                    onChange={(event) => setLogin(event.target.value)}
                    placeholder="Логин клиента в Директе"
                    pattern="[A-Za-z0-9][A-Za-z0-9._@-]{0,254}"
                    maxLength={255}
                    autoComplete="off"
                    required
                  />
                  <div className="project-settings-actions">
                    <button
                      type="submit"
                      className="button button-primary"
                      disabled={saving || !login.trim()}
                    >
                      {saving ? "Сохраняем…" : "Сохранить логин"}
                    </button>
                    {binding.client_login && (
                      <button
                        type="button"
                        className="button button-quiet"
                        disabled={saving}
                        onClick={() => setConfirmUnlink(true)}
                      >
                        Отвязать
                      </button>
                    )}
                  </div>
                </form>
              )}
              {confirmUnlink && !archived && (
                <div className="confirmation-panel">
                  <p>Убрать логин Директа из проекта? История останется.</p>
                  <div className="project-settings-actions">
                    <button
                      type="button"
                      className="button button-primary"
                      disabled={saving}
                      onClick={() => void unlink()}
                    >
                      Да, отвязать
                    </button>
                    <button
                      type="button"
                      className="button button-quiet"
                      disabled={saving}
                      onClick={() => setConfirmUnlink(false)}
                    >
                      Отмена
                    </button>
                  </div>
                </div>
              )}
            </>
          )}
          {notice && <p role="status" className="direct-notice">{notice}</p>}
          {error && <div role="alert" className="error-message">{error}</div>}
        </div>
      )}
    </div>
  );
}
