import { defineConfig } from '@playwright/test'

// Runs the real app (FastAPI serving the built SPA) against a throwaway SQLite DB.
export default defineConfig({
  testDir: '.',
  timeout: 90_000,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: 'http://localhost:8123',
    viewport: { width: 1360, height: 900 },
    launchOptions: { executablePath: process.env.CHROME_PATH || undefined },
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: 'rm -f e2e.db && DATABASE_URL=sqlite:///./e2e.db uv run uvicorn app.main:app --port 8123',
    cwd: '../backend',
    url: 'http://localhost:8123/healthz',
    reuseExistingServer: false,
    timeout: 60_000,
  },
})
