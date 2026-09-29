import forecastJson from "@/data/generated/forecast.json";
import teamsJson from "@/data/generated/teams.json";
import matchupsJson from "@/data/generated/matchups.json";
import tournamentJson from "@/data/generated/tournament.json";
import methodologyJson from "@/data/generated/methodology.json";
import type {
  Envelope, ForecastData, ForecastTeam, MatchupData, MethodologyData, SimTeam, TeamStage1, TournamentData,
} from "./types";

export const forecast = forecastJson as unknown as Envelope<ForecastData>;
export const teamsEnv = teamsJson as unknown as Envelope<{ teams: TeamStage1[] }>;
export const matchups = matchupsJson as unknown as Envelope<MatchupData>;
export const tournament = tournamentJson as unknown as Envelope<TournamentData>;
export const methodology = methodologyJson as unknown as Envelope<MethodologyData>;

export const freeze = forecast.data.freeze;


/** Teams ordered by frozen championship probability (as stored in PRIMARY_FORECAST.csv). */
export const teamsByChampion: ForecastTeam[] = [...forecast.data.teams].sort(
  (a, b) => b.championship_probability - a.championship_probability,
);

export const teamIds = teamsByChampion.map((t) => t.id);

export function getTeam(id: string): ForecastTeam | undefined {
  return forecast.data.teams.find((t) => t.id === id);
}

export function getStage1(id: string): TeamStage1 | undefined {
  return teamsEnv.data.teams.find((t) => t.id === id);
}

export function getSim(id: string): SimTeam | undefined {
  return tournament.data.simulated.teams.find((t) => t.id === id);
}

/** Frozen series win probability that team a beats team b (lookup only; never recomputed). */
export function seriesProbability(aId: string, bId: string): number | null {
  const i = matchups.data.team_order_ids.indexOf(aId);
  const j = matchups.data.team_order_ids.indexOf(bId);
  if (i < 0 || j < 0 || i === j) return null;
  return matchups.data.bo5[i][j];
}

export function stage1Fixtures(id: string) {
  return matchups.data.stage1_ledger
    .filter((r) => r.team_a_id === id || r.team_b_id === id)
    .map((r) => {
      const home = r.team_a_id === id;
      return {
        date: r.scheduled_date,
        key: r.ledger_key,
        opponentId: home ? r.team_b_id : r.team_a_id,
        opponentName: home ? r.team_b : r.team_a,
        p: home ? r.p_team_a : r.p_team_b,
      };
    });
}

