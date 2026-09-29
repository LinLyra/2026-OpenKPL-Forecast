#!/usr/bin/env node
/**
 * Presentation assets from the official KPL site (https://kpl.qq.com), fetched through the same public
 * endpoints its front end uses. Writes images to public/assets/kpl/ and a manifest to data/assets/kpl-official.json.
 * Nothing here feeds any forecast. Teams or players the endpoint does not return stay absent.
 *
 *   node scripts/fetch-kpl-assets.mjs
 */
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const API = "https://kplshop-op.timi-esports.qq.com/kplow";
const HEADERS = { Referer: "https://kpl.qq.com/", "User-Agent": "Mozilla/5.0 OpenKPL-portfolio" };
const OUT_IMG = path.join(ROOT, "public/assets/kpl");
const OUT_JSON = path.join(ROOT, "data/assets/kpl-official.json");

// Official Chinese team names -> site team ids (names as listed in data/teamPresentation.ts).
const TEAM_IDS = {
  重庆狼队: "wolves", 成都AG超玩会: "ag", 北京JDG: "jdg", 广州TTG: "ttg", KSG: "ksg", 北京WB: "wb",
  "长沙TES.A": "tesa", "上海EDG.M": "edgm", "杭州LGD.NBW": "lgd-nbw", 深圳DYG: "dyg", 济南RW侠: "rw", 南通Hero久竞: "hero",
};
// `position` codes as labelled by the same site's getTeamsIntro.position_cn (KPL2026S2).
const POSITION = { 1: "clash", 2: "mid", 3: "farm", 4: "jungle", 5: "roam" };

const getJson = async (url) => {
  const res = await fetch(url, { headers: HEADERS });
  if (!res.ok) throw new Error(`${res.status} ${url}`);
  const body = await res.json();
  if (body.result !== 0) throw new Error(`result ${body.result} ${url}`);
  return body.data;
};

async function download(url, file) {
  if (!url) return null;
  const res = await fetch(url, { headers: HEADERS });
  if (!res.ok) return null;
  const ext = (/\.(png|jpe?g|webp)(\?|$)/i.exec(url)?.[1] ?? "png").toLowerCase().replace("jpeg", "jpg");
  const abs = path.join(OUT_IMG, `${file}.${ext}`);
  await fs.mkdir(path.dirname(abs), { recursive: true });
  await fs.writeFile(abs, Buffer.from(await res.arrayBuffer()));
  return `/assets/kpl/${file}.${ext}`;
}

const list = await getJson(`${API}/getTeamsList`);
const season = list[0]?.teamid.split("_")[0] ?? null;
const teams = {};
for (const t of list) {
  const id = TEAM_IDS[t.team_name];
  if (!id) continue;
  const intro = await getJson(`${API}/getTeamsIntro?teamid=${encodeURIComponent(t.teamid)}&seasonid=${season}`).catch(() => null);
  const players = [];
  for (const p of t.player_list ?? []) {
    players.push({
      playerId: p.playerid,
      name: p.short_name,
      realName: p.real_name || null,
      position: POSITION[p.position] ?? null,
      playerPortrait: await download(p.avatar, `${id}/players/${p.playerid}`),
    });
  }
  teams[id] = {
    officialName: t.team_name,
    kplTeamId: t.teamid,
    slogan: intro?.team_info?.slogan || null,
    teamLogo: await download(t.team_logo, `${id}/logo`),
    teamLogoAlt: await download(t.team_logo_2, `${id}/logo-alt`),
    teamPhoto: await download(t.img, `${id}/photo`),
    teamHeroImage: null,
    coachPortrait: null,
    players,
  };
  console.log(`${id.padEnd(8)} ${t.team_name} logo=${!!teams[id].teamLogo} photo=${!!teams[id].teamPhoto} players=${players.length}`);
}

await fs.mkdir(path.dirname(OUT_JSON), { recursive: true });
await fs.writeFile(OUT_JSON, JSON.stringify({
  source: "KPL 官网 https://kpl.qq.com (kplow/getTeamsList, kplow/getTeamsIntro)",
  season,
  fetched_at: new Date().toISOString(),
  teams,
}, null, 2) + "\n");
console.log(`wrote ${path.relative(ROOT, OUT_JSON)} (${Object.keys(teams).length} teams)`);
