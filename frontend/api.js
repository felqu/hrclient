// The API serves these pages on its own origin, including direct launch on :8090.
// The Docker frontend on :5173 talks to the API on :8000.
(() => {
  const location = window.location;
  let base = `${location.origin}/api/v1`;
  if (location.protocol === "file:") {
    base = "http://localhost:8000/api/v1";
  } else if (location.port === "5173") {
    base = `${location.protocol}//${location.hostname}:8000/api/v1`;
  }
  window.HRClientApi = {
    url: (window.HR_CLIENT_API_URL || base).replace(/\/+$/, ""),
  };
})();
