const API_URL = window.HR_CLIENT_API_URL || "http://localhost:8000/api/v1";

const byId = (id) => document.getElementById(id);
const today = new Date();
const sevenDaysAgo = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000);
const asDate = (date) => date.toISOString().slice(0, 10);

byId("date-from").value = asDate(sevenDaysAgo);
byId("date-to").value = asDate(today);

async function request(path, options) {
  const response = await fetch(`${API_URL}${path}`, options);
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

function showError(element, error) {
  element.textContent = `Ошибка: ${error.message}`;
}

function renderMetrics(metrics) {
  byId("sent").textContent = metrics.total_sent;
  byId("viewed").textContent = metrics.viewed;
  byId("invited").textContent = metrics.invited;
  byId("rejected").textContent = metrics.rejected;
}

function renderVacancies(vacancies) {
  const container = byId("vacancies");
  const status = byId("vacancies-status");
  container.replaceChildren();
  if (!vacancies.length) {
    status.textContent = "Пока нет импортированных вакансий. Задайте диапазон дат и запустите импорт.";
    return;
  }
  status.textContent = "";
  vacancies.forEach((vacancy) => {
    const card = document.createElement("article");
    const source = document.createElement("span");
    source.className = "tag";
    source.textContent = vacancy.source;
    const title = document.createElement("h3");
    title.textContent = vacancy.title;
    const company = document.createElement("p");
    company.textContent = vacancy.company || "Компания не указана";
    const link = document.createElement("a");
    link.href = vacancy.url;
    link.target = "_blank";
    link.rel = "noreferrer";
    link.textContent = "Открыть вакансию";
    card.append(source, title, company, link);
    container.append(card);
  });
}

async function loadDashboard() {
  try {
    renderMetrics(await request("/analytics/dashboard"));
  } catch (error) {
    ["sent", "viewed", "invited", "rejected"].forEach((id) => { byId(id).textContent = "—"; });
    console.error(error);
  }
}

async function loadVacancies() {
  const status = byId("vacancies-status");
  try {
    renderVacancies(await request("/vacancies"));
  } catch (error) {
    showError(status, error);
  }
}

byId("import-button").addEventListener("click", async () => {
  const button = byId("import-button");
  const status = byId("import-status");
  button.disabled = true;
  status.textContent = "Ставим импорт в очередь…";
  try {
    await request("/vacancies/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        date_from: `${byId("date-from").value}T00:00:00Z`,
        date_to: `${byId("date-to").value}T23:59:59Z`,
        sources: ["hh", "telegram"],
      }),
    });
    status.textContent = "Импорт поставлен в очередь";
    await loadVacancies();
  } catch (error) {
    showError(status, error);
  } finally {
    button.disabled = false;
  }
});

loadDashboard();
loadVacancies();
