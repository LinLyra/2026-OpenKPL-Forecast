#!/usr/bin/env node
/**
 * Browser smoke check against a running server (default http://127.0.0.1:3417; override with BASE_URL).
 * Uses the locally installed Google Chrome via playwright-core; no browser download, no external network.
 * Reports console errors/warnings, uncaught exceptions and horizontal overflow at desktop (1440) and mobile (390).
 */
import { chromium } from "playwright-core";

const BASE = process.env.BASE_URL ?? "http://127.0.0.1:3417";
const PAGES = [
  "/zh", "/zh/tournament", "/zh/teams", "/zh/teams/wolves", "/zh/teams/wolves/journey", "/zh/teams/dyg",
  "/zh/matchup", "/zh/methodology", "/en", "/en/tournament", "/en/teams", "/en/teams/ag",
  "/en/teams/ag/journey", "/en/matchup", "/en/methodology",
];

const browser = await chromium.launch({ channel: "chrome" });
let failures = 0;

for (const width of [1440, 390]) {
  const ctx = await browser.newContext({ viewport: { width, height: 900 } });
  for (const path of PAGES) {
    const page = await ctx.newPage();
    const issues = [];
    page.on("console", (m) => { if (m.type() === "error" || m.type() === "warning") issues.push(`${m.type()}: ${m.text().slice(0, 200)}`); });
    page.on("pageerror", (e) => issues.push(`pageerror: ${e.message.slice(0, 200)}`));
    const res = await page.goto(BASE + path, { waitUntil: "networkidle" });
    await page.waitForTimeout(600);
    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    if (scrollWidth > width) issues.push(`horizontal overflow: scrollWidth ${scrollWidth} > ${width}`);
    if (res?.status() !== 200) issues.push(`HTTP ${res?.status()}`);
    failures += issues.length;
    console.log(`${width}px ${path.padEnd(18)} ${issues.length ? issues.join(" | ") : "OK"}`);
    await page.close();
  }
  await ctx.close();
}

const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
await page.goto(`${BASE}/zh/tournament`, { waitUntil: "networkidle" });
await page.getByRole("button", { name: /北京JDG 14\.2%/ }).click();
await page.locator('svg [role="button"]').nth(5).click();
await page.waitForTimeout(300);
const pathTeamSelected = await page.getByRole("button", { name: /北京JDG 14\.2%/ }).getAttribute("aria-pressed") === "true";
const knockoutDetail = await page.getByText("胜者组", { exact: true }).isVisible();
if (!pathTeamSelected || !knockoutDetail) failures++;
console.log(`tournament path interaction ${pathTeamSelected && knockoutDetail ? "OK" : "FAIL"}`);

await page.goto(`${BASE}/zh/matchup`, { waitUntil: "networkidle" });
const matchupState = async () => {
  const teams = await page.locator("select").evaluateAll((els) => els.map((e) => e.value));
  const probs = (await page.locator("p.display-num").allInnerTexts()).slice(0, 2);
  return { teams, probs };
};
const before = await matchupState();
await page.getByRole("button", { name: /交换/ }).click();
await page.waitForTimeout(900);
const after = await matchupState();
const swapped =
  before.teams.length === 2 && after.teams[0] === before.teams[1] && after.teams[1] === before.teams[0] &&
  after.probs[0] === before.probs[1] && after.probs[1] === before.probs[0];
if (!swapped) failures++;
console.log(`matchup swap ${swapped ? "OK" : "FAIL"}: ${before.teams.join(" vs ")} ${before.probs.join(" / ")} -> ${after.teams.join(" vs ")} ${after.probs.join(" / ")}`);
await page.locator("select").first().selectOption("jdg");
await page.waitForTimeout(900);
const picked = await matchupState();
if (picked.teams[0] !== "jdg") failures++;
console.log(`matchup pick: ${picked.teams.join(" vs ")} ${picked.probs.join(" / ")}`);

await browser.close();
console.log(failures ? `FAILED: ${failures} issue(s)` : "SMOKE CHECK PASSED");
process.exit(failures ? 1 : 0);
