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

const transliteration: Record<string, string> = {
  а: "a", б: "b", в: "v", г: "g", д: "d", е: "e", ё: "yo", ж: "zh",
  з: "z", и: "i", й: "y", к: "k", л: "l", м: "m", н: "n", о: "o",
  п: "p", р: "r", с: "s", т: "t", у: "u", ф: "f", х: "h", ц: "ts",
  ч: "ch", ш: "sh", щ: "sch", ъ: "", ы: "y", ь: "", э: "e", ю: "yu", я: "ya",
};

function projectCodeFromName(name: string): string {
  return name
    .toLowerCase()
    .split("")
    .map((letter) => transliteration[letter] ?? letter)
    .join("")
    .normalize("NFKD")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80)
    .replace(/-+$/g, "");
}

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
  const [loadedOrganizationId, setLoadedOrganizationId] = useState("");
  const [projectReload, setProjectReload] = useState(0);
  const [showCreate, setShowCreate] = useState(false);
  const [projectName, setProjectName] = useState("");
  const [projectCode, setProjectCode] = useState("");
  const [projectCodeTouched, setProjectCodeTouched] = useState(false);
  const [projectBusy, setProjectBusy] = useState(false);
  const [projectError, setProjectError] = useState("");
  const [projectNotice, setProjectNotice] = useState("");
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
      setLoadedOrganizationId("");
      return;
    }
    let active = true;
    // Never display projects from the previously selected organization while loading.
    setProjects([]);
    setLoadedOrganizationId("");
    setLoadingProjects(true);
    setError("");
    void getJSON<Project[]>(`/organizations/${organizationId}/projects`)
      .then((data) => {
        if (active) {
          setProjects(data);
          setLoadedOrganizationId(organizationId);
        }
      })
      .catch(() => {
        if (active) {
          setProjects([]);
          setLoadedOrganizationId(organizationId);
          setError("Не удалось получить список проектов.");
        }
      })
      .finally(() => { if (active) setLoadingProjects(false); });
    return () => { active = false; };
  }, [view, organizationId, projectReload]);

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
      setLoadedOrganizationId("");
      setOrganizationId("");
      setView("login");
    } catch {
      setError("Ошибка выхода. Попробуй ещё раз.");
    } finally {
      setBusy(false);
    }
  }

  async function createProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const selectedOrganization = organizations.find((org) => org.id === organizationId);
    if (!selectedOrganization || !["owner", "admin"].includes(selectedOrganization.role)) {
      setProjectError("Недостаточно прав для создания проекта.");
      return;
    }
    setProjectBusy(true);
    setProjectError("");
    setProjectNotice("");
    try {
      const response = await fetch(api + `/organizations/${organizationId}/projects`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: projectName.trim(), slug: projectCode.trim() }),
      });
      if (response.status === 409) {
        setProjectError("Такой код проекта уже используется в организации.");
        return;
      }
      if (response.status === 422) {
        setProjectError("Проверь название и код: 3–80 символов, латинские буквы, цифры и дефис.");
        return;
      }
      if (response.status === 401) {
        setProjectError("Сессия истекла. Войди заново.");
        return;
      }
      if (response.status === 403 || response.status === 404) {
        setProjectError("Нет доступа к созданию проекта в выбранной организации.");
        return;
      }
      if (!response.ok) throw new Error("Could not create project");
      const created = (await response.json()) as Project;
      setProjectNotice(`Проект «${created.name}» создан. Он пока пустой.`);
      setShowCreate(false);
      setProjectName("");
      setProjectCode("");
      setProjectCodeTouched(false);
      setProjectReload((value) => value + 1);
    } catch {
      setProjectError("Не удалось создать проект. Проверь подключение к backend.");
    } finally {
      setProjectBusy(false);
    }
  }

  // Compare organization IDs during render; old-tenant cards never flash on switch.
  const displayedProjects = loadedOrganizationId === organizationId ? projects : [];
  const projectLoading = loadingProjects || (!!organizationId && loadedOrganizationId !== organizationId);
  const currentOrganization = organizations.find((org) => org.id === organizationId);
  const canCreate = currentOrganization?.role === "owner" || currentOrganization?.role === "admin";

  return (
    <main className="shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-icon">✳</span> MAKO
          <span className="brand-light">INTELLIGENCE</span>
        </div>
        <div className="header-right">
          <span className="version">CORE / B2.3</span>
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
                onChange={(e) => {
                  setOrganizationId(e.target.value);
                  setShowCreate(false);
                  setProjectName("");
                  setProjectCode("");
                  setProjectCodeTouched(false);
                  setProjectError("");
                  setProjectNotice("");
                }}
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

          <div className="section-top">
            <h2>Проекты</h2>
            <div className="project-header-actions">
              <span>{displayedProjects.length} доступно</span>
              {canCreate && (
                <button
                  className="button button-primary create-trigger"
                  type="button"
                  onClick={() => {
                    setShowCreate((open) => !open);
                    setProjectError("");
                    setProjectNotice("");
                  }}
                >
                  {showCreate ? "Отмена" : "+ Новый проект"}
                </button>
              )}
            </div>
          </div>
          {canCreate && showCreate && (
            <form className="create-panel" onSubmit={createProject}>
              <div>
                <span className="eyebrow">НОВЫЙ РЕКЛАМНЫЙ ПРОЕКТ</span>
                <h3>Добавить проект</h3>
                <p className="muted">Пока создаётся пустая карточка без подключения рекламных кабинетов.</p>
              </div>
              <div className="create-fields">
                <div>
                  <label htmlFor="new-project-name" className="field-label">Название</label>
                  <input
                    className="form-input"
                    id="new-project-name"
                    value={projectName}
                    onChange={(e) => {
                      setProjectName(e.target.value);
                      if (!projectCodeTouched) setProjectCode(projectCodeFromName(e.target.value));
                    }}
                    placeholder="Например, Еврофлетт"
                    maxLength={200}
                    required
                  />
                </div>
                <div>
                  <label htmlFor="new-project-code" className="field-label">Код проекта</label>
                  <input
                    className="form-input"
                    id="new-project-code"
                    value={projectCode}
                    onChange={(e) => {
                      setProjectCodeTouched(true);
                      setProjectCode(e.target.value.toLowerCase());
                    }}
                    placeholder="euroflett"
                    minLength={3}
                    maxLength={80}
                    pattern="[a-z0-9][a-z0-9-]{1,78}[a-z0-9]"
                    title="От 3 до 80 символов: латинские буквы, цифры и дефис. Без дефиса в начале или конце."
                    required
                  />
                </div>
              </div>
              {projectError && <div role="alert" className="error-message">{projectError}</div>}
              <button
                className="button button-primary"
                type="submit"
                disabled={projectBusy || !organizationId}
              >
                {projectBusy ? "Создаём…" : "Создать проект"}
              </button>
            </form>
          )}
          {projectNotice && <div role="status" className="success-message">{projectNotice}</div>}
          {error && <div role="alert" className="error-message">{error}</div>}
          {projectLoading && <p className="muted">Загружаем проекты…</p>}
          {!projectLoading && !organizations.length && (
            <p className="empty-state">У пользователя пока нет организаций.</p>
          )}
          {!projectLoading && organizations.length > 0 && displayedProjects.length === 0 && (
            <p className="empty-state">Нет доступных проектов в этой организации.</p>
          )}
          <div className="project-grid">
            {!projectLoading && displayedProjects.map((project) => (
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

      <footer>MAKO Intelligence · B2.3 · Только локальная разработка</footer>
    </main>
  );
}
