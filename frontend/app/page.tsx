"use client";

import { useEffect, useState } from "react";

type ServiceStatus = "checking" | "online" | "offline";

const roadmap = [
  { number: "01", title: "Core", status: "В работе", detail: "API, база данных, локальный запуск, тесты" },
  { number: "02", title: "Insight", status: "Запланировано", detail: "Дашборд и прозрачные рекламные метрики" },
  { number: "03", title: "Audit", status: "Запланировано", detail: "Правила диагностики и доказательные находки" },
  { number: "04", title: "Optimizer / Experiments / Signal", status: "Позже", detail: "Оптимизация, сайты и ML-конверсии" },
];

export default function Home() {
  const [api, setApi] = useState<ServiceStatus>("checking");
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

  useEffect(() => {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5000);
    fetch(apiUrl + "/healthz", { signal: controller.signal, cache: "no-store" })
      .then((res) => { if (!res.ok) throw new Error("API unavailable"); return res.json(); })
      .then((body) => setApi(body.status === "ok" ? "online" : "offline"))
      .catch(() => setApi("offline"))
      .finally(() => clearTimeout(timeout));
    return () => { controller.abort(); clearTimeout(timeout); };
  }, [apiUrl]);

  const label = api === "checking" ? "Проверяем API" : api === "online" ? "API работает" : "API недоступен";

  return (
    <main className="shell">
      <header className="topbar">
        <div className="brand"><span className="brand-icon">✳</span> MAKO <span className="brand-light">INTELLIGENCE</span></div>
        <div className="version">CORE / 0.1.0</div>
      </header>

      <section className="intro">
        <div className="eyebrow">ПЛАТФОРМА PERFORMANCE-МАРКЕТИНГА</div>
        <h1>Разбираемся в данных.<br/><span>Находим решения.</span></h1>
        <p>Мы начали строить единую платформу аналитики, диагностики и оптимизации рекламы. Сейчас это локальный технический каркас, а не подключённый кабинет клиента.</p>
        <div className="actions">
          <span className={["pill", api].join(" ")}><span className="dot" />{label}</span>
          <span className="pill neutral">Без клиентских данных</span>
          <span className="pill neutral">Без платных API</span>
        </div>
      </section>

      <section className="section">
        <div className="section-top"><h2>План разработки</h2><span>Первые проверяемые этапы</span></div>
        <div className="roadmap">
          {roadmap.map((item) => (
            <article className="milestone" key={item.number}>
              <div className="number">{item.number}</div>
              <div className="milestone-body"><h3>{item.title}</h3><p>{item.detail}</p></div>
              <span className="state">{item.status}</span>
            </article>
          ))}
        </div>
      </section>
      <footer>MAKO Intelligence · Milestone A · Только локальная разработка</footer>
    </main>
  );
}
