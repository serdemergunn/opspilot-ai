// Captures the README screenshots from a running stack.
//
//   docker compose up -d          (repository root)
//   cd scripts/screenshots && npm ci && npm run capture
//
// Uses an installed Chromium-based browser (Edge or Chrome); set BROWSER_PATH to override.
// Demo mode is used, so the answers shown are deterministic and labeled as such in the UI.

import { existsSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer-core";

const here = dirname(fileURLToPath(import.meta.url));
const OUT = resolve(here, "../../docs/screenshots");
const BASE = process.env.BASE_URL ?? "http://127.0.0.1:3000";
const CANDIDATES = [
  process.env.BROWSER_PATH,
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "/usr/bin/google-chrome",
  "/usr/bin/chromium",
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
].filter(Boolean);

const executablePath = CANDIDATES.find((p) => existsSync(p));
if (!executablePath) throw new Error("No Chromium-based browser found; set BROWSER_PATH.");
mkdirSync(OUT, { recursive: true });

const browser = await puppeteer.launch({
  executablePath,
  headless: true,
  defaultViewport: { width: 1440, height: 960, deviceScaleFactor: 1.5 },
});

async function ask(page, question) {
  await page.goto(`${BASE}/analyst`, { waitUntil: "networkidle0" });
  await page.type("#question", question);
  await page.keyboard.press("Enter");
  await page.waitForSelector('[aria-label="Findings"]', { timeout: 30_000 });
  await page.waitForSelector('[aria-label="Charts"] svg', { timeout: 10_000 });
  await new Promise((r) => setTimeout(r, 600)); // let charts finish layout
  await page.evaluate(() => window.scrollTo(0, 0));
}

// Grow the viewport to the page height instead of using fullPage, so viewport-height elements
// (the sidebar, the sticky evidence panel) span the whole image.
async function tallShot(page, path) {
  // Layouts sized in vh grow with the viewport, so repeat until the page fits.
  let height = 960;
  for (let i = 0; i < 6; i++) {
    await page.setViewport({ width: 1440, height, deviceScaleFactor: 1.5 });
    await new Promise((r) => setTimeout(r, 400));
    const needed = await page.evaluate(() => document.documentElement.scrollHeight);
    if (needed <= height) break;
    height = needed;
  }
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path });
  await page.setViewport({ width: 1440, height: 960, deviceScaleFactor: 1.5 });
}

try {
  const page = await browser.newPage();

  // 1. Overview dashboard: full page, all charts.
  await page.goto(`${BASE}/`, { waitUntil: "networkidle0" });
  await page.waitForFunction(() => document.querySelectorAll(".recharts-surface").length >= 3, { timeout: 30_000 });
  await new Promise((r) => setTimeout(r, 600));
  await tallShot(page, `${OUT}/overview.png`);

  // 2. AI Analyst: the Phase 1 acceptance question.
  await ask(page, "Which production line had the most downtime last week?");
  await page.screenshot({ path: `${OUT}/ai-analyst.png` });

  // 3. AI Analyst: a multi-tool question with a derived calculation and a labeled hypothesis.
  await ask(page, "Why did production efficiency decrease yesterday?");
  await tallShot(page, `${OUT}/ai-analyst-multi-tool.png`);

  console.log(`Saved screenshots to ${OUT} using ${executablePath}`);
} finally {
  await browser.close();
}
