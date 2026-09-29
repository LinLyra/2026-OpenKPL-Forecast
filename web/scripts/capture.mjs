#!/usr/bin/env node
/**
 * Visual QA capture: node scripts/capture.mjs <outDir> <name=path@WxH[+full][!action]>...
 * Actions (optional, after "!"): "role:<name>" clicks a role button, "state:<label>" clicks a state tab.
 * Requires Google Chrome and a running server (BASE_URL, default http://127.0.0.1:3418).
 */
import { chromium } from "playwright-core";
import path from "node:path";

const BASE = process.env.BASE_URL ?? "http://127.0.0.1:3418";
const [outDir, ...specs] = process.argv.slice(2);
const browser = await chromium.launch({ channel: "chrome", headless: true });

for (const spec of specs) {
  const eq = spec.indexOf("=");
  const name = spec.slice(0, eq);
  const rest = spec.slice(eq + 1);
  const [target, ...actions] = rest.split("!");
  const [route, size] = target.split("@");
  const full = size.endsWith("+full");
  const [w, h] = size.replace("+full", "").split("x").map(Number);
  const page = await browser.newPage({ viewport: { width: w, height: h } });
  await page.goto(BASE + route, { waitUntil: "networkidle" });
  await page.waitForTimeout(1500);
  for (const a of actions) {
    const [kind, label] = a.split(":");
    if (kind === "role") await page.getByRole("button", { name: label, exact: false }).first().click();
    if (kind === "state") await page.getByRole("tab", { name: label, exact: false }).first().click();
    await page.waitForTimeout(1800);
  }
  if (full) {
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.waitForTimeout(300);
  }
  const file = path.join(outDir, `${name}.png`);
  await page.screenshot({ path: file, fullPage: full });
  const width = await page.evaluate(() => document.documentElement.scrollWidth);
  console.log(`${name}: ${file} (scrollWidth ${width}/${w})`);
  await page.close();
}
await browser.close();
