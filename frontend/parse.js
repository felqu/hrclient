const API_URL = window.HR_CLIENT_API_URL || "http://localhost:8000/api/v1";

const byId = (id) => document.getElementById(id);
const today = new Date();
const sevenDaysAgo = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000);
const asDate = (date) => date.toISOString().slice(0, 10);

byId("date-from").value = asDate(sevenDaysAgo);
byId("date-to").value = asDate(today);

function setStatus(element, message, isError, withSpinner) {
  element.classList.toggle("error", Boolean(isError));
  element.replaceChildren();
  if (withSpinner) {
    const spinner = document.createElement("span");
    spinner.className = "spinner";
    element.append(spinner);
  }
  element.append(document.createTextNode(message));
}

function showError(element, error) {
  setStatus(element, `Ошибка: ${error.message}`, true, false);
}

function salaryText(vacancy) {
  const salary = vacancy.salary;
  if (!salary) return null;
  const currency = salary.currency || "RUB";
  if (salary.min_amount != null && salary.max_amount != null) {
    return `${salary.min_amount}–${salary.max_amount} ${currency}`;
  }
  if (salary.min_amount != null) return `от ${salary.min_amount} ${currency}`;
  if (salary.max_amount != null) return `до ${salary.max_amount} ${currency}`;
  return salary.raw_text || null;
}

function renderVacancies(vacancies) {
  const container = byId("vacancies");
  const status = byId("vacancies-status");
  container.replaceChildren();
  if (!vacancies.length) {
    status.textContent = "Ничего не найдено. Попробуйте другие каналы или более широкий диапазон дат.";
    return;
  }
  status.textContent = "";

  vacancies.forEach((vacancy) => {
    const card = document.createElement("article");

    const source = document.createElement("span");
    source.className = "tag";
    source.textContent = (vacancy.source && vacancy.source.channel_name) || "telegram";

    const title = document.createElement("h3");
    title.textContent = vacancy.title || "Вакансия";

    const company = document.createElement("p");
    company.textContent =
      vacancy.company && vacancy.company.name
        ? `Компания: ${vacancy.company.name}`
        : "Компания не указана";

    card.append(source, title, company);

    const salary = salaryText(vacancy);
    if (salary) {
      const salaryNode = document.createElement("p");
      salaryNode.className = "salary";
      salaryNode.textContent = salary;
      card.append(salaryNode);
    }

    const tags = [vacancy.work_format, vacancy.employment_type, vacancy.experience_level, vacancy.location]
      .filter(Boolean);
    if (tags.length) {
      const tagRow = document.createElement("div");
      tagRow.className = "tags";
      tags.forEach((value) => {
        const tag = document.createElement("span");
        tag.className = "tag";
        tag.textContent = value;
        tagRow.append(tag);
      });
      card.append(tagRow);
    }

    const url = vacancy.source && (vacancy.source.original_url || vacancy.source.channel_url);
    if (url) {
      const link = document.createElement("a");
      link.href = url;
      link.target = "_blank";
      link.rel = "noreferrer";
      link.textContent = "Открыть в Telegram";
      card.append(link);
    }

    if (vacancy.published_date) {
      const published = document.createElement("p");
      published.textContent = `Опубликовано: ${vacancy.published_date}`;
      card.append(published);
    }

    if (vacancy.raw_text) {
      const details = document.createElement("details");
      const summary = document.createElement("summary");
      summary.textContent = "Текст сообщения";
      const pre = document.createElement("pre");
      pre.textContent = vacancy.raw_text;
      details.append(summary, pre);
      card.append(details);
    }

    container.append(card);
  });
}

byId("parse-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = byId("run-button");
  const status = byId("parse-status");
  const vacanciesStatus = byId("vacancies-status");

  const chats = byId("chats")
    .value.split(/[\n,;]+/)
    .map((value) => value.trim())
    .filter(Boolean);
  if (!chats.length) {
    setStatus(status, "Укажите хотя бы один канал", true, false);
    return;
  }

  button.disabled = true;
  byId("vacancies").replaceChildren();
  vacanciesStatus.textContent = "";
  setStatus(status, "Идёт парсинг…", false, true);

  try {
    const response = await fetch(`${API_URL}/parse`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        chats,
        backend: byId("backend").value,
        date_from: byId("date-from").value,
        date_to: byId("date-to").value,
        text: byId("text").value.trim() || null,
        max_per_channel: parseInt(byId("max").value, 10) || null,
      }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = data.detail;
      const message = typeof detail === "string" ? detail : JSON.stringify(detail || `HTTP ${response.status}`);
      throw new Error(message);
    }
    renderVacancies(data.vacancies);
    setStatus(
      status,
      `Готово: найдено ${data.count} вакансий за ${(data.duration_ms / 1000).toFixed(1)} с`,
      false,
      false,
    );
  } catch (error) {
    showError(status, error);
    vacanciesStatus.textContent = "Парсинг не завершился — результаты недоступны.";
  } finally {
    button.disabled = false;
  }
});
