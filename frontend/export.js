// Both pages download the same persistent collection.
const exportButton = document.getElementById("export-button");
const exportStatus = document.getElementById("export-status");
let exportObjectUrl = null;
const downloadLink = document.createElement("a");
downloadLink.textContent = "Скачать XLSX";
downloadLink.hidden = true;
exportStatus.after(downloadLink);

exportButton.addEventListener("click", async () => {
  exportButton.disabled = true;
  exportStatus.textContent = "Готовим XLSX…";
  try {
    const apiUrl = window.HRClientApi.url;
    const response = await fetch(`${apiUrl}/vacancies/export.xlsx`);
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(typeof data.detail === "string" ? data.detail : `HTTP ${response.status}`);
    }
    const contentType = response.headers.get("Content-Type") || "";
    if (!contentType.includes("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")) {
      throw new Error("API вернул не XLSX. Проверьте, что запущен app.api.parse_api:app");
    }
    const blob = await response.blob();
    if (exportObjectUrl) URL.revokeObjectURL(exportObjectUrl);
    exportObjectUrl = URL.createObjectURL(blob);
    downloadLink.href = exportObjectUrl;
    const disposition = response.headers.get("Content-Disposition") || "";
    const filename = /filename="([^"]+)"/.exec(disposition);
    downloadLink.download = filename ? filename[1] : "vacancies.xlsx";
    downloadLink.hidden = false;
    downloadLink.click();
    exportStatus.textContent = "XLSX готов. Если скачивание не началось, нажмите «Скачать XLSX».";
  } catch (error) {
    exportStatus.textContent = `Ошибка выгрузки: ${error.message}`;
  } finally {
    exportButton.disabled = false;
  }
});

window.addEventListener("beforeunload", () => {
  if (exportObjectUrl) URL.revokeObjectURL(exportObjectUrl);
});
