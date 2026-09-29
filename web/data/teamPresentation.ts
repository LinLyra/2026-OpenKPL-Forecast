/**
 * Presentation-layer team data (never affects any probability): official Chinese name, group, city.
 * displayNameEn values are UI transliterations of the official Chinese names, not official English names.
 * Logos, photos and rosters come from lib/assets.ts (official KPL site); absent means hidden.
 */
import type { Group } from "@/lib/types";

export type Position = "clash" | "jungle" | "mid" | "farm" | "roam";
export const POSITIONS: Position[] = ["clash", "jungle", "mid", "farm", "roam"];

export interface TeamPresentation {
  id: string;
  displayNameZh: string;
  displayNameEn: string;
  shortName: string;
  group: Group;
  city?: string;
}

export const teamPresentation: Record<string, TeamPresentation> = {
  wolves: { id: "wolves", displayNameZh: "重庆狼队", displayNameEn: "Chongqing Wolves", shortName: "狼队", group: "MASTER", city: "重庆" },
  ag: { id: "ag", displayNameZh: "成都AG超玩会", displayNameEn: "Chengdu AG", shortName: "AG", group: "MASTER", city: "成都" },
  jdg: { id: "jdg", displayNameZh: "北京JDG", displayNameEn: "Beijing JDG", shortName: "JDG", group: "MASTER", city: "北京" },
  ttg: { id: "ttg", displayNameZh: "广州TTG", displayNameEn: "Guangzhou TTG", shortName: "TTG", group: "MASTER", city: "广州" },
  ksg: { id: "ksg", displayNameZh: "KSG", displayNameEn: "KSG", shortName: "KSG", group: "MASTER" },
  wb: { id: "wb", displayNameZh: "北京WB", displayNameEn: "Beijing WB", shortName: "WB", group: "MASTER", city: "北京" },
  tesa: { id: "tesa", displayNameZh: "长沙TES.A", displayNameEn: "Changsha TES.A", shortName: "TES.A", group: "ELITE", city: "长沙" },
  edgm: { id: "edgm", displayNameZh: "上海EDG.M", displayNameEn: "Shanghai EDG.M", shortName: "EDG.M", group: "ELITE", city: "上海" },
  "lgd-nbw": { id: "lgd-nbw", displayNameZh: "杭州LGD.NBW", displayNameEn: "Hangzhou LGD.NBW", shortName: "LGD", group: "ELITE", city: "杭州" },
  dyg: { id: "dyg", displayNameZh: "深圳DYG", displayNameEn: "Shenzhen DYG", shortName: "DYG", group: "ELITE", city: "深圳" },
  rw: { id: "rw", displayNameZh: "济南RW侠", displayNameEn: "Jinan RW", shortName: "RW侠", group: "ELITE", city: "济南" },
  hero: { id: "hero", displayNameZh: "南通Hero久竞", displayNameEn: "Nantong Hero", shortName: "Hero", group: "ELITE", city: "南通" },
};

export function presentation(id: string): TeamPresentation {
  const p = teamPresentation[id];
  if (!p) throw new Error(`no presentation entry for team ${id}`);
  return p;
}
