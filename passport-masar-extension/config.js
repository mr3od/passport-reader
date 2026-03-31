// ─── Environment config ───────────────────────────────────────────────────────
// Switch between dev and prod by commenting/uncommenting one line,
// or run:  ./scripts/use-dev.sh  /  ./scripts/use-prod.sh

// const API_BASE_URL = "http://127.0.0.1:8000"; // DEV
const API_BASE_URL = "https://passport-api.mr3od.dev"; // PROD

globalThis.API_BASE_URL = API_BASE_URL;
