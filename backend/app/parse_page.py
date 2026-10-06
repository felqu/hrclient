#!/usr/bin/env python3
"""Простая HTML-страничка: запускает парсинг вакансий из Telegram и показывает результат.

Запуск (без установки дополнительных зависимостей):
    cd backend
    ../.venv/bin/python -m app.parse_page
    → открыть http://127.0.0.1:8040

Параметры окружения:
    PARSE_PAGE_HOST, PARSE_PAGE_PORT — адрес/порт (по умолчанию 127.0.0.1:8040).
    TG_BACKEND, TG_API_ID, TG_API_HASH — см. app.integrations.sources.
"""
from __future__ import annotations

import asyncio
import json
import os
import traceback
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from app.integrations.sources import TelegramGateway

HOST = os.getenv("PARSE_PAGE_HOST", "127.0.0.1")
PORT = int(os.getenv("PARSE_PAGE_PORT", "8040"))

PAGE_TEMPLATE = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Парсинг вакансий из Telegram</title>
<style>
  :root { --accent:#2563eb; --bg:#f5f6f8; --card:#fff; --line:#e3e6ea; --muted:#6b7280; --danger:#dc2626; }
  * { box-sizing:border-box; }
  body { margin:0; font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; background:var(--bg); color:#111827; }
  main { max-width:960px; margin:0 auto; padding:24px 16px 64px; }
  h1 { font-size:22px; margin:0 0 4px; }
  .subtitle { color:var(--muted); margin:0 0 20px; font-size:14px; }
  .panel { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px; margin-bottom:24px; }
  label { display:block; font-size:13px; color:var(--muted); margin-bottom:10px; }
  textarea, input, select { width:100%; margin-top:4px; padding:8px 10px; border:1px solid var(--line); border-radius:8px; font:inherit; background:#fff; }
  textarea { resize:vertical; font-family:ui-monospace,Menlo,monospace; font-size:13px; }
  .row { display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:12px; margin-top:4px; }
  button { margin-top:6px; background:var(--accent); color:#fff; border:0; border-radius:8px; padding:10px 18px; font:inherit; font-weight:600; cursor:pointer; }
  button:disabled { opacity:.6; cursor:wait; }
  .status { margin-top:12px; font-size:14px; white-space:pre-wrap; }
  .status.error { color:var(--danger); }
  .spinner { display:inline-block; width:12px; height:12px; margin-right:6px; border:2px solid rgba(37,99,235,.3); border-top-color:var(--accent); border-radius:50%; animation:spin .7s linear infinite; vertical-align:-1px; }
  @keyframes spin { to { transform:rotate(360deg); } }
  .cards { display:grid; grid-template-columns:repeat(auto-fill,minmax(420px,1fr)); gap:16px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px; display:flex; flex-direction:column; gap:8px; }
  .card h3 { margin:0; font-size:16px; }
  .tag { display:inline-block; background:#eff6ff; color:#1d4ed8; border-radius:999px; padding:2px 10px; font-size:12px; margin-right:6px; }
  .meta { color:var(--muted); font-size:13px; margin:0; }
  .salary { font-weight:600; color:#047857; margin:0; font-size:15px; }
  .card a { color:var(--accent); font-size:14px; }
  details { margin-top:auto; }
  summary { cursor:pointer; color:var(--muted); font-size:13px; }
  pre { white-space:pre-wrap; word-break:break-word; background:#f9fafb; border:1px solid var(--line); border-radius:8px; padding:10px; font-size:12px; max-height:260px; overflow:auto; }
  .empty { color:var(--muted); font-size:14px; }
</style>
</head>
<body>
<main>
  <h1>Парсинг вакансий из Telegram</h1>
  <p class="subtitle">Запуск синхронного парсинга каналов и отображение найденных вакансий без сохранения в БД.</p>

  <section class="panel">
    <label>Каналы (по одному в строке или через запятую)
      <textarea id="chats" rows="3" placeholder="telegram&#10;hh_vacancies&#10;@job_channel"></textarea>
    </label>
    <div class="row">
      <label>Парсер
        <select id="backend">
          <option value="tg_parser">tg_parser (tgscraper, публичные)</option>
          <option value="private_tg_parser">private_tg_parser (Telethon, нужны TG_API_ID/HASH)</option>
        </select>
      </label>
      <label>Дата от <input id="date-from" type="date"/></label>
      <label>Дата до <input id="date-to" type="date"/></label>
      <label>Слова в тексте <input id="text" type="text" placeholder="необязательно"/></label>
      <label>Сообщений / канал <input id="max" type="number" value="200" min="1"/></label>
    </div>
    <button id="run" type="button">Запустить парсинг</button>
    <p id="status" class="status" hidden></p>
  </section>

  <section id="results"></section>
</main>
<script>
  const $ = (id) => document.getElementById(id);
  const pad = (n) => String(n).padStart(2, "0");
  const asDate = (d) => `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`;

  const now = new Date();
  const weekAgo = new Date(now.getTime() - 7 * 864e5);
  $("date-from").value = asDate(weekAgo);
  $("date-to").value = asDate(now);

  const el = (tag, cls, text) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  };
  const displayName = (v) => (v.company && typeof v.company === "object" ? v.company.name : (v.company || null));
  const salaryText = (v) => {
    const s = v.salary;
    if (!s) return null;
    if (s.min_amount != null && s.max_amount != null) return `${s.min_amount}–${s.max_amount} ${s.currency || "RUB"}`;
    if (s.min_amount != null) return `от ${s.min_amount} ${s.currency || "RUB"}`;
    return s.raw_text || (s.max_amount != null ? `до ${s.max_amount} ${s.currency || "RUB"}` : null);
  };
  const linkOf = (v) => (v.source && typeof v.source === "object") ? (v.source.original_url || v.source.channel_url) : null;

  function render(list) {
    const box = $("results");
    box.replaceChildren();
    if (!list.length) {
      box.append(el("p", "empty", "Ничего не найдено — попробуйте другие каналы или более широкий диапазон дат."));
      return;
    }
    const grid = el("div", "cards");
    list.forEach((v) => {
      const card = el("article", "card");
      card.append(el("span", "tag", (v.source && v.source.channel_name) || "telegram"));
      card.append(el("h3", "", v.title || "Вакансия"));
      const company = displayName(v);
      if (company) card.append(el("p", "meta", `Компания: ${company}`));
      const salary = salaryText(v);
      if (salary) card.append(el("p", "salary", salary));
      const tags = [v.work_format, v.employment_type, v.experience_level].filter(Boolean);
      if (v.location) tags.unshift(v.location);
      if (tags.length) {
        const row = el("div");
        tags.forEach((t) => row.append(el("span", "tag", String(t))));
        card.append(row);
      }
      const url = linkOf(v);
      if (url) {
        const a = document.createElement("a");
        a.href = url; a.target = "_blank"; a.rel = "noreferrer";
        a.textContent = "Открыть в Telegram";
        card.append(a);
      }
      if (v.published_date) card.append(el("p", "meta", `Опубликовано: ${v.published_date}`));
      if (v.raw_text) {
        const details = document.createElement("details");
        details.append(document.createElement("summary"));
        details.querySelector("summary").textContent = "Текст сообщения";
        details.append(el("pre", "", v.raw_text));
        card.append(details);
      }
      grid.append(card);
    });
    box.append(grid);
  }

  function setStatus(message, isError) {
    const status = $("status");
    status.hidden = false;
    status.classList.toggle("error", Boolean(isError));
    if (isError) {
      status.replaceChildren(el("span", "", message));
    } else {
      status.replaceChildren(
        el("span", "spinner"),
        el("span", "", message),
      );
    }
  }

  $("run").addEventListener("click", async () => {
    const button = $("run");
    button.disabled = true;
    $("results").replaceChildren();
    setStatus("Идёт парсинг…");
    try {
      const chats = $("chats").value.split(/[\\n,;]+/).map((s) => s.trim()).filter(Boolean);
      if (!chats.length) throw new Error("Укажите хотя бы один канал.");
      const payload = {
        chats,
        backend: $("backend").value,
        date_from: $("date-from").value || asDate(weekAgo),
        date_to: $("date-to").value || asDate(now),
        text: $("text").value.trim() || null,
        max_per_channel: parseInt($("max").value, 10) || null,
      };
      const response = await fetch("/api/parse", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) throw new Error(data.error || `HTTP ${response.status}`);
      render(data.vacancies || []);
      setStatus(`Готово: найдено вакансий — ${data.count}, заняло ${(data.duration_ms / 1000).toFixed(1)} с.`);
    } catch (error) {
      setStatus(`Ошибка: ${error.message}`, true);
    } finally {
      $("status").querySelectorAll(".spinner").forEach((s) => s.remove());
      button.disabled = false;
    }
  });
</script>
</body>
</html>
"""


def _dump(model: Any) -> Any:
    """Сериализация pydantic-модели в JSON-совместимые данные (v1 и v2)."""
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return json.loads(model.json())


def _parse_dt(value: str | None, default: datetime) -> datetime:
    if not value:
        return default
    value = str(value).strip()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        pass
    try:
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return default


async def _run_parse(payload: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    chats = [str(c).strip() for c in payload.get("chats") or []]
    if not chats:
        raise ValueError("Не указаны каналы")

    gateway = TelegramGateway(
        chats=chats,
        backend=payload.get("backend") or None,
        max_per_channel=payload.get("max_per_channel") or None,
    )
    vacancies = await gateway.search(
        date_from=_parse_dt(payload.get("date_from"), now - timedelta(days=7)),
        date_to=_parse_dt(payload.get("date_to"), now),
        text=payload.get("text") or None,
    )
    return {"chats": chats, "vacancies": [_dump(v) for v in vacancies]}


class Handler(BaseHTTPRequestHandler):
    server_version = "ParsePage/0.1"

    def _send_json(self, status: int, data: dict[str, Any]) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if urlparse(self.path).path != "/":
            self._send_json(404, {"ok": False, "error": "Not found"})
            return
        self._send_html(PAGE_TEMPLATE)

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/parse":
            self._send_json(404, {"ok": False, "error": "Not found"})
            return
        try:
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")) or 0)
            payload = json.loads(raw or b"{}")
        except (ValueError, KeyError):
            self._send_json(400, {"ok": False, "error": "Некорректный JSON"})
            return

        started = datetime.now(timezone.utc)
        try:
            result = asyncio.run(_run_parse(payload))
            elapsed_ms = (datetime.now(timezone.utc) - started).total_seconds() * 1000
            self._send_json(200, {
                "ok": True,
                "count": len(result["vacancies"]),
                "duration_ms": round(elapsed_ms),
                "chats": result["chats"],
                "vacancies": result["vacancies"],
            })
        except Exception as error:  # noqa: BLE001
            traceback.print_exc()
            self._send_json(500, {"ok": False, "error": str(error)})

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[{self.address_string()}] {format % args}")


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Открыть страницу парсинга: http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nОстановлено.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()