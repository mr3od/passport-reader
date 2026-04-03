// ─── Environment config ───────────────────────────────────────────────────────
// Switch between prod and local development by commenting/uncommenting one line.

const API_BASE_URL = "https://passport-api.mr3od.dev"; // PROD
// const API_BASE_URL = "http://127.0.0.1:8000"; // DEV

globalThis.API_BASE_URL = API_BASE_URL;
