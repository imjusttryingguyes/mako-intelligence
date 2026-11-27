"use client";

import { useState } from "react";

type Campaign = { id: number; name: string };
type Preview = { count: number; fetched_at: string; campaigns: Campaign[] };
type Props = { organizationId: string; projectId: string };

const api = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const PAGE_SIZE = 25;

export default function DirectCampaignPreview({ organizationId, projectId }: Props) {
  const [data, setData] = useState<Preview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);

  async function load() {
    if (busy) return;
    setBusy(true);
    setError("");
    setData(null);
    setSearch("");
    setPage(0);
    try {
      const response = await fetch(
        `${api}/organizations/${organizationId}/projects/${projectId}/direct-campaign-preview`,
        { method: "POST", credentials: "include", cache: "no-store" }
      );
      if (response.status === 409) {
        setError("Сначала повторно проверь доступ к рекламодателю или обнови настройки проекта.");
        return;
      }
      if (response.status === 401 || response.status === 403 || response.status === 404) {
        setError("Нет доступа к списку кампаний или истекла сессия.");
        return;
      }
      if (response.status === 502 || response.status === 503) {
        setError("Не удалось получить кампании из Директа. Проверь токен, права и доступность API.");
        return;
      }
      if (!response.ok) throw new Error("Campaign preview failed");
      const preview = (await response.json()) as Preview;
      setData(preview);
    } catch {
      setError("Ошибка загрузки кампаний. Проверь подключение к backend.");
    } finally {
      setBusy(false);
    }
  }

  const normalized = search.trim().toLocaleLowerCase("ru-RU");
  const filtered = data
    ? data.campaigns.filter((campaign) =>
        campaign.name.toLocaleLowerCase("ru-RU").includes(normalized)
        || String(campaign.id).includes(normalized))
    : [];
  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount - 1);
  const displayed = filtered.slice(currentPage * PAGE_SIZE, (currentPage + 1) * PAGE_SIZE);

  return (
    <section className="direct-campaign-preview" aria-label="Кампании Яндекс Директа">
      <div className="eyebrow">КАМПАНИИ · ТОЛЬКО ЧТЕНИЕ</div>
      <p className="direct-disclaimer">
        Список запрашивается только по нажатию. Названия и ID не сохраняются в MAKO.
      </p>
      <button
        type="button"
        className="button button-quiet"
        onClick={() => void load()}
        disabled={busy}
      >
        {busy ? "Загружаем кампании…" : data ? "Обновить список кампаний" : "Показать кампании"}
      </button>
      {error && <div className="error-message" role="alert">{error}</div>}
      {data && (
        <div className="campaign-results">
          <p className="direct-disclaimer">
            Получено: <strong>{data.count}</strong> ·{" "}
            {new Date(data.fetched_at).toLocaleString("ru-RU")}
          </p>
          <label htmlFor={`campaign-search-${projectId}`} className="field-label">
            Поиск по названию или ID
          </label>
          <input
            id={`campaign-search-${projectId}`}
            className="form-input"
            type="search"
            value={search}
            placeholder="Найти кампанию"
            onChange={(event) => { setSearch(event.target.value); setPage(0); }}
          />
          <p className="direct-disclaimer">
            {filtered.length === 0 ? "Совпадений нет" : `Найдено: ${filtered.length}`}
          </p>
          <ul className="campaign-preview-list">
            {displayed.map((campaign) => (
              <li key={campaign.id} className="campaign-preview-row">
                <span className="campaign-preview-name">{campaign.name}</span>
                <span className="campaign-preview-id">ID {campaign.id}</span>
              </li>
            ))}
          </ul>
          {pageCount > 1 && (
            <div className="campaign-preview-pagination">
              <button
                type="button"
                className="button button-quiet"
                disabled={currentPage === 0}
                onClick={() => setPage((value) => Math.max(0, value - 1))}
              >
                Назад
              </button>
              <span>{currentPage + 1} / {pageCount}</span>
              <button
                type="button"
                className="button button-quiet"
                disabled={currentPage >= pageCount - 1}
                onClick={() => setPage((value) => Math.min(pageCount - 1, value + 1))}
              >
                Далее
              </button>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
