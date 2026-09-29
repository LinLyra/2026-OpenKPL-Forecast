import Link from "next/link";
import { getSim, getStage1, stage1Fixtures } from "@/lib/data";
import { teamAssets } from "@/lib/assets";
import { mmdd, pct } from "@/lib/format";
import { dict, href, teamName, type Locale } from "@/lib/i18n";
import { POSITIONS, presentation } from "@/data/teamPresentation";
import { Panel, PanelTitle, TeamLogo } from "@/components/common/ui";
import { PlayerCard } from "../PlayerCard";

export function TeamOverview({ locale, teamId }: { locale: Locale; teamId: string }) {
  const t = dict(locale);
  const sim = getSim(teamId)!;
  const s1 = getStage1(teamId)!;
  const fixtures = stage1Fixtures(teamId);
  const maxRank = Math.max(...s1.p_group_rank);
  const players = [...(teamAssets(teamId)?.players ?? [])].sort(
    (a, b) => POSITIONS.indexOf(a.position ?? "roam") - POSITIONS.indexOf(b.position ?? "roam"),
  );
  const path = [sim.p_direct_knockout, sim.p_knockout, sim.p_upper_semifinal, sim.p_final, sim.p_champion];

  return (
    <div className="space-y-6">
      <Panel>
        <PanelTitle title={t.profile.path} />
        <ol className="grid grid-cols-2 gap-y-6 sm:grid-cols-5">
          {path.map((v, i) => (
            <li key={i} className="relative pr-4">
              <span className={`block h-0.5 rounded-full ${i === 4 ? "bg-gold" : "bg-ink-700"}`}>
                <span className="block h-full rounded-full bg-gold" style={{ width: `${v * 100}%` }} />
              </span>
              <p className={`mt-3 ${i === 4 ? "gold-num" : "num font-semibold text-fg"} text-h1 leading-tight`}>{pct(v)}</p>
              <p className="mt-1 text-caption text-mute">{t.profile.pathStages[i]}</p>
            </li>
          ))}
        </ol>
      </Panel>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
        <Panel>
          <PanelTitle title={t.profile.schedule} />
          <ul className="space-y-2.5">
            {fixtures.map((f) => {
              const op = presentation(f.opponentId);
              return (
                <li key={f.key}>
                  <Link href={href(locale, `/teams/${f.opponentId}`)} className="flex items-center gap-3 rounded-xl bg-ink-850/70 px-4 py-3 transition-colors hover:bg-ink-800">
                    <span className="num w-11 text-caption text-mute">{mmdd(f.date)}</span>
                    <TeamLogo id={f.opponentId} size={36} />
                    <span className="min-w-0 flex-1 truncate text-body font-medium">{teamName(locale, op.displayNameZh, op.displayNameEn)}</span>
                    <span className="num text-h3 font-semibold text-gold-soft">{pct(f.p)}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </Panel>

        <Panel className="flex flex-col">
          <PanelTitle title={t.profile.rankDist} />
          <div className="flex min-h-40 flex-1 items-end gap-2">
            {s1.p_group_rank.map((v, i) => (
              <div key={i} className="flex h-full flex-1 flex-col items-center justify-end gap-2">
                <span className="num text-caption font-semibold">{pct(v, 0)}</span>
                <span className="w-full rounded-t-md" style={{ height: `${Math.max((v / maxRank) * 70, 1.5)}%`, background: i < 2 ? "linear-gradient(#f3dca4,#a97c3a)" : "#1d2a47" }} />
                <span className="text-micro text-mute">{t.profile.rank1(i + 1)}</span>
              </div>
            ))}
          </div>
          <div className="mt-6 grid grid-cols-2 gap-4 border-t border-line pt-5">
            <div>
              <p className="text-caption text-mute">{t.profile.expectedWins}</p>
              <p className="num text-h2 font-semibold">{s1.expected_series_wins.toFixed(1)}<span className="text-body text-mute"> / {fixtures.length}</span></p>
            </div>
            <div>
              <p className="text-caption text-mute">{t.profile.expectedGd}</p>
              <p className="num text-h2 font-semibold">{s1.expected_game_diff > 0 ? "+" : ""}{s1.expected_game_diff.toFixed(1)}</p>
            </div>
          </div>
        </Panel>
      </div>

      {players.length > 0 && (
        <Panel>
          <PanelTitle title={t.profile.roster} sub={t.profile.rosterSource} />
          <div className="grid grid-cols-3 gap-x-4 gap-y-8 sm:grid-cols-4 lg:grid-cols-7">
            {players.map((p) => <PlayerCard key={p.playerId} player={p} locale={locale} />)}
          </div>
        </Panel>
      )}
    </div>
  );
}
