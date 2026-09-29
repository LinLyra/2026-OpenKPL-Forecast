import official from "@/data/assets/kpl-official.json";
import type { Position } from "@/data/teamPresentation";

/** Visual asset fields. `null` = no verified asset; the UI hides the element rather than drawing a stand-in. */
export interface PlayerAssets {
  playerId: string;
  name: string;
  realName: string | null;
  position: Position | null;
  playerPortrait: string | null;
}

export interface TeamAssets {
  officialName: string;
  slogan: string | null;
  teamLogo: string | null;
  teamLogoAlt: string | null;
  teamHeroImage: string | null;
  teamPhoto: string | null;
  coachPortrait: string | null;
  players: PlayerAssets[];
}

const teams = official.teams as unknown as Record<string, TeamAssets>;

export const assetSource = { source: official.source, season: official.season };

export function teamAssets(id: string): TeamAssets | null {
  return teams[id] ?? null;
}
