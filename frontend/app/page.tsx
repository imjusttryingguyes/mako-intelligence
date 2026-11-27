"use client";

import { useEffect, useState, type FormEvent } from "react";

type View = "loading" | "login" | "dashboard";
type User = { id: string; email: string; display_name: string };
type Organization = { id: string; slug: string; name: string; role: string };
type Project = {
  id: string;
  slug: string;
  name: string;
  status: "active" | "archived";
  actions: string[];
};

const api = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function getJSON<T>(path: string): Promise<T> {
  const response = await fetch(api + path, { credentials: "include", cache: "no-store" });
  if (!response.ok) throw new Error("API request failed");
  return (await response.json()) as T;
}

export default function Home() {
  const [view, setView] = useState<View>("loading");
  const [user, setUser] = useState<User | null>(null);
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [organizationId, setOrganizationId] = useState("");
  const [projects, setProjects] = useState<Project[]>([]);
  const [loadingProjects, setLoadingProjects] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    async function restoreSession() {
      try {
        const res = await fetch(api + "/auth/me", {
          credentials: "include",
          cache: "no-store",
        });
        if (!active) return;
        if (res.status === 401) {
          setView("login");
          return;
        }
        if (!res.ok) throw new Error("API unavailable");
        const profile = (await res.json()) as User;
        const orgs = await getJSON<Organization[]>("/organizations");
        if (!active) return;
        setUser(profile);
        setOrganizations(orgs);
        setOrganizationId(orgs[0]?.id ?? "");
        setView("dashboard");
      } catch {
        if (active) {
          setError("Не удалось подключиться к API. Проверь Docker Desktop.");
          setView("login");
        }
      }
    }
    void restoreSession();
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (view !== "dashboard" || !organizationId) {
      setProjects([]);
      return;
    }
    let active = true;
    setLoadingProjects(true);
    setError("");
    void getJSON<Project[]>(`/organizations/${organizationId}/projects`)
      .then((data) => { if (active) setProjects(data); })
      .catch(() => { if (active) setError("Не удалось получить список проектов."); })
      .finally(() => { if (active) setLoadingProjects(false); });
    return () => { active = false; };
  }, [view, organizationId]);

  async function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const response = await fetch(api + "/auth/login", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      if (response.status === 401) {
        setError("Неверная почта или пароль.");
        return;
      }
      if (!response.ok) throw new Error("Login unavailable");
      const profile = (await response.json()) as User;
      const orgs = await getJSON<Organization[]>("/organizations");
      setUser(profile);
      setOrganizations(orgs);
      setOrganizationId(orgs[0]?.id ?? "");
      setPassword("");
      setView("dashboard");
    } catch {
      setError("Не удалось войти. Проверь работу backend.");
    } finally {
      setBusy(false);
    }
  }

  async function signOut() {
    setBusy(true);
    setError("");
    try {
      const response = await fetch(api + "/auth/logout", {
        method: "POST",
        credentials: "include",
      });
      if (!response.ok) throw new Error("Logout failed");
      setUser(null);
      setOrganizations([]);
      setProjects([]);
      setOrganizationId("");
      setView("login");
    } catch {
      setError("Ошибка выхода. Попробуй ещё раз.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-icon">✳</span> MAKO
          <span className="brand-light">INTELLIGENCE</span>
        </div>
        <div className="header-right">
          <span className="version">CORE / B2.2</span>
          {view === "dashboard" && (
            <button className="button button-quiet" disabled={busy} onClick={signOut}>
              Выйти
            </button>
          )}
        </div>
      </header>

      {view === "loading" && (
        <section className="loading-panel" aria-live="polite">
          <span className="eyebrow">ПОДКЛЮЧЕНИЕ К ПЛАТФОРМЕ</span>
          <h1>Проверяем сессию…</h1>
        </section>
      )}

      {view === "login" && (
        <section className="login-layout">
          <div className="login-story">
            <div className="eyebrow">ЛОКАЛЬНАЯ ВЕРСИЯ · MILESTONE B2</div>
            <h1>Твои проекты.<br /><span>Твои решения.</span></h1>
            <p>Первый защищённый вход в MAKO Intelligence. Доступ к рекламным данным пока не подключён — здесь мы готовим пространство для будущей аналитики.</p>
            <div className="actions">
              <span className="pill neutral">Локальная разработка</span>
              <span className="pill neutral">Без платных API</span>
            </div>
          </div>

          <form className="login-panel" onSubmit={signIn}>
            <span className="eyebrow">ВХОД В СИСТЕМУ</span>
            <h2>С возвращением</h2>
            <p>Используй почту и пароль, заданные при первоначальной настройке.</p>
            <label className="field-label" htmlFor="email">Электронная почта</label>
            <input
              className="form-input"
              id="email"
              type="email"
              autoComplete="username"
              value={email}
              maxLength={320}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              required
            />
            <label className="field-label" htmlFor="password">Пароль</label>
            <input
              className="form-input"
              id="password"
              type="password"
              autoComplete="current-password"
              value={password}
              maxLength={128}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Твой пароль"
              required
            />
            {error && <div role="alert" className="error-message">{error}</div>}
            <button className="button button-primary" type="submit" disabled={busy}>
              {busy ? "Входим…" : "Войти в MAKO"}
            </button>
            <p className="form-note">Ещё нет аккаунта? Создай локального владельца через терминал VS Code по инструкции в README.</p>
          </form>
        </section>
      )}

      {view === "dashboard" && (
        <section className="dashboard">
          <div className="eyebrow">РАБОЧЕЕ ПРОСТРАНСТВО</div>
          <h1>Привет, <span>{user?.display_name}</span></h1>
          <p className="intro-copy">Это твои доступные проекты. Позже здесь появятся показатели Директа, диагностика и рекомендации MAKO Intelligence.</p>

          <div className="dashboard-toolbar">
            <div>
              <span className="field-label">Организация</span>
              <select
                aria-label="Организация"
                className="form-input org-select"
                value={organizationId}
                onChange={(e) => setOrganizationId(e.target.value)}
              >
                {organizations.map((organization) => (
                  <option value={organization.id} key={organization.id}>
                    {organization.name} · {organization.role}
                  </option>
                ))}
              </select>
            </div>
            <span className="pill neutral">Режим: просмотр</span>
          </div>

          <div className="section-top"><h2>Проекты</h2><span>{projects.length} доступно</span></div>
          {error && <div role="alert" className="error-message">{error}</div>}
          {loadingProjects && <p className="muted">Загружаем проекты…</p>}
          {!loadingProjects && !organizations.length && (
            <p className="empty-state">У пользователя пока нет организаций.</p>
          )}
          {!loadingProjects && organizations.length > 0 && projects.length === 0 && (
            <p className="empty-state">Нет доступных проектов в этой организации.</p>
          )}
          <div className="project-grid">
            {!loadingProjects && projects.map((project) => (
              <article key={project.id} className="project-card">
                <div className="project-card-top">
                  <span className="project-avatar">{project.name.slice(0, 1).toUpperCase()}</span>
                  <span className="pill neutral">
                    {project.status === "active" ? "Активен" : "В архиве"}
                  </span>
                </div>
                <h3>{project.name}</h3>
                <p>Проект · {project.slug}</p>
                <div className="permissions">
                  {project.actions.includes("manage_members")
                    ? "Управление проектом"
                    : project.actions.includes("edit") ? "Редактирование" : "Только просмотр"}
                </div>
              </article>
            ))}
          </div>
          <p className="dashboard-footnote">Демонстрационный проект не содержит реальных рекламных данных. Доступ определяется сервером.</p>
        </section>
      )}

      <footer>MAKO Intelligence · B2.2 · Только локальная разработка</footer>
    </main>
  );
}
