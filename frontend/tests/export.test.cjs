const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = (name) => fs.readFileSync(path.join(__dirname, "..", name), "utf8");
const xlsxType = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

function browser(url, override) {
  const window = { location: new URL(url), HR_CLIENT_API_URL: override, addEventListener() {} };
  const context = vm.createContext({ window });
  vm.runInContext(source("api.js"), context);
  return context;
}

function exportPage(response, url = "http://127.0.0.1:8090/parse.html") {
  const context = browser(url);
  let clickHandler;
  let requestedUrl;
  let clicks = 0;
  const revoked = [];
  const button = { disabled: false, addEventListener(event, callback) { clickHandler = callback; } };
  const status = { textContent: "", after() {} };
  const link = { click() { clicks++; } };
  Object.assign(context, {
    document: {
      getElementById(id) { return id === "export-button" ? button : status; },
      createElement() { return link; },
    },
    fetch: async (url) => { requestedUrl = url; return response; },
    URL: { createObjectURL() { return "blob:test-download"; }, revokeObjectURL(url) { revoked.push(url); } },
  });
  vm.runInContext(source("export.js"), context);
  return { click: () => clickHandler(), button, status, link, revoked,
    requestedUrl: () => requestedUrl, clicks: () => clicks };
}

test("API follows the page origin on 8090 and 8000", () => {
  for (const port of ["8090", "8000"]) {
    assert.equal(browser(`http://127.0.0.1:${port}/parse.html`).window.HRClientApi.url,
      `http://127.0.0.1:${port}/api/v1`);
  }
});

test("separate Docker frontend, file pages and explicit API overrides resolve correctly", () => {
  assert.equal(browser("http://127.0.0.1:5173/").window.HRClientApi.url, "http://127.0.0.1:8000/api/v1");
  assert.equal(browser("file:///tmp/parse.html").window.HRClientApi.url, "http://localhost:8000/api/v1");
  assert.equal(browser("http://localhost:8090/", "https://api.example.com/api/v1/").window.HRClientApi.url,
    "https://api.example.com/api/v1");
});

test("export button downloads from 8090 and leaves a usable manual download link", async () => {
  const page = exportPage({ ok: true, headers: { get(name) { return name === "Content-Type"
    ? xlsxType : 'attachment; filename="vacancies-2026-10-14.xlsx"'; } }, blob: async () => ({}) });
  await page.click();
  assert.equal(page.requestedUrl(), "http://127.0.0.1:8090/api/v1/vacancies/export.xlsx");
  assert.equal(page.clicks(), 1);
  assert.equal(page.link.download, "vacancies-2026-10-14.xlsx");
  assert.equal(page.link.href, "blob:test-download");
  assert.equal(page.link.hidden, false);
  assert.equal(page.button.disabled, false);
  assert.deepEqual(page.revoked, []);
  await page.click();
  assert.deepEqual(page.revoked, ["blob:test-download"]);
});

test("server error is shown and the export button can be retried", async () => {
  const page = exportPage({ ok: false, status: 500, json: async () => ({ detail: "Ошибка XLSX" }) });
  await page.click();
  assert.match(page.status.textContent, /Ошибка XLSX/);
  assert.equal(page.clicks(), 0);
  assert.equal(page.button.disabled, false);
});

test("an HTML page from the wrong server is not downloaded as an XLSX", async () => {
  const page = exportPage({ ok: true, headers: { get() { return "text/html"; } } });
  await page.click();
  assert.match(page.status.textContent, /API вернул не XLSX/);
  assert.equal(page.clicks(), 0);
  assert.equal(page.button.disabled, false);
});
