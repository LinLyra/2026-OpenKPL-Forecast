"use client";

import { AnimatePresence, motion } from "framer-motion";
import { Fragment, useState } from "react";
import { getSim, getStage1, tournament } from "@/lib/data";
import { mmdd, pct } from "@/lib/format";
import { dict, type Locale } from "@/lib/i18n";
import type { SimTeam, StageKey } from "@/lib/types";
import { TeamSelect } from "@/components/common/TeamSelect";
import { Panel, PanelTitle } from "@/components/common/ui";
import { ProbabilityFlow, type FlowNodeId } from "./ProbabilityFlow";

export function TournamentJourney({ locale, initialTeam = "wolves", showSelector = true }: { locale: Locale; initialTeam?: string; showSelector?: boolean }) {
  const t = dict(locale);
  const [teamId, setTeamId] = useState(initialTeam);
  const [hovered, setHovered] = useState<FlowNodeId | null>(null);
  const sim = getSim(teamId)!;

  return (
    <div className="space-y-6">
      {showSelector && <Structure locale={locale} />}

      <Panel>
        <PanelTitle title={t.tournament.flow} sub={t.tournament.flowSub}
          right={showSelector ? <TeamSelect locale={locale} value={teamId} onChange={setTeamId} label={t.tournament.select} className="w-full sm:w-72" /> : undefined} />
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_15rem]">
          <div className="min-w-0 overflow-x-auto">
            <ProbabilityFlow sim={sim} locale={locale} hovered={hovered} onHover={setHovered} />
          </div>
          <StageDetail sim={sim} node={hovered} locale={locale} />
        </div>
      </Panel>

      <div className="grid gap-6 lg:grid-cols-1">
        <KnockoutPaths sim={sim} locale={locale} />
      </div>
    </div>
  );
}

function Structure({ locale }: { locale: Locale }) {
  const t = dict(locale);
  const st = tournament.data.structure;
  const byKey = Object.fromEntries(st.stages.map((s) => [s.key, s])) as Record<StageKey, (typeof st.stages)[number]>;
  const range = (k: StageKey) => `${mmdd(byKey[k].dates[0])}–${mmdd(byKey[k].dates[1])}`;
  const cols = [
    { key: "stage1", title: t.stages.stage1, sub: t.stageFormat.stage1, date: range("stage1") },
    { key: "split", title: `${t.stages.direct} / ${t.stages.breakthrough}`, sub: t.stageFormat.breakthrough, date: range("breakthrough") },
    { key: "knockout", title: t.stages.knockout, sub: t.stageFormat.knockout, date: range("knockout") },
    { key: "final", title: t.stages.final, sub: t.stageFormat.final, date: mmdd(byKey.final.dates[0]) },
  ];
  return (
    <Panel>
      <PanelTitle title={t.tournament.structure} />
      <ol className="flex flex-col gap-2 md:flex-row md:items-stretch">
        {cols.map((c, i) => (
          <Fragment key={c.key}>
            {i > 0 && <li aria-hidden className="hidden items-center text-gold/60 md:flex">→</li>}
            <li className={`flex-1 rounded-xl px-4 py-3 ${c.key === "final" ? "border border-gold/50 bg-gold/10" : "bg-ink-850/80"}`}>
              <p className="num text-caption text-gold">{c.date}</p>
              <p className="mt-1 text-body font-semibold">{c.title}</p>
              <p className="text-caption text-mute">{c.sub}</p>
            </li>
          </Fragment>
        ))}
      </ol>
    </Panel>
  );
}

function StageDetail({ sim, node, locale }: { sim: SimTeam; node: FlowNodeId | null; locale: Locale }) {
  const t = dict(locale), tt = t.tournament;
  const st = getStage1(sim.id)!;
  const stages = tournament.data.structure.stages;
  const s = (k: StageKey) => stages.find((x) => x.key === k)!;
  const date = (k: StageKey) => (s(k).dates[0] === s(k).dates[1] ? mmdd(s(k).dates[0]) : `${mmdd(s(k).dates[0])}–${mmdd(s(k).dates[1])}`);
  const outKo = sim.terminal.LB_R1 + sim.terminal.LB_R2 + sim.terminal.LB_SF + sim.terminal.LB_F;

  type Info = { stage: string; format?: string; dates?: string; prob: number; risk?: [string, number]; notes: string[] };
  const info: Record<FlowNodeId, Info> = {
    stage1: { stage: t.stages.stage1, format: t.stageFormat.stage1, dates: date("stage1"), prob: 1, risk: [tt.riskStage1, sim.p_stage1_elimination],
      notes: [`${t.profile.expectedWins}: ${st.expected_series_wins.toFixed(1)} / 6`] },
    direct: { stage: t.stages.direct, format: t.stageFormat.stage1, dates: date("stage1"), prob: sim.p_direct_knockout, notes: [] },
    breakthrough: { stage: t.stages.breakthrough, format: t.stageFormat.breakthrough, dates: date("breakthrough"), prob: sim.p_breakthrough,
      risk: [tt.riskBreakthrough, sim.p_eliminated_in_breakthrough_given_entry], notes: [] },
    out_s1: { stage: `${t.stages.stage1} · ${t.stages.eliminated}`, prob: sim.terminal.STAGE1, notes: [tt.stage1Only] },
    out_bt: { stage: `${t.stages.breakthrough} · ${t.stages.eliminated}`, prob: sim.terminal.BREAKTHROUGH, notes: [] },
    knockout: { stage: t.stages.knockout, format: t.stageFormat.knockout, dates: date("knockout"), prob: sim.p_knockout, risk: [tt.riskKnockout, outKo],
      notes: [`${tt.championGivenKnockout}: ${pct(sim.p_champion_given_knockout)}`] },
    out_ko: { stage: `${t.stages.knockout} · ${t.stages.eliminated}`, prob: outKo, notes: [] },
    final: { stage: t.stages.final, format: t.stageFormat.final, dates: date("final"), prob: sim.p_final, risk: [tt.riskFinal, sim.terminal.FINAL], notes: [] },
    runner: { stage: t.stages.runnerUp, prob: sim.terminal.FINAL, notes: [] },
    champion: { stage: t.stages.champion, prob: sim.p_champion, notes: [] },
  };
  const i = info[node ?? "champion"];

  return (
    <aside className="rounded-xl bg-ink-850/80 p-5" aria-live="polite">
      {!node && <p className="text-micro text-faint">{tt.hover}</p>}
      <AnimatePresence mode="wait">
        <motion.div key={`${sim.id}-${node}`} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.18 }}>
          <p className="mt-1 text-h3 font-semibold">{i.stage}</p>
          {i.format && (
            <dl className="mt-2 space-y-1 text-caption">
              <div className="flex justify-between gap-3"><dt className="text-mute">{tt.format}</dt><dd className="text-right">{i.format}</dd></div>
              <div className="flex justify-between gap-3"><dt className="text-mute">{tt.dates}</dt><dd className="num">{i.dates}</dd></div>
            </dl>
          )}
          <p className={`mt-4 text-display leading-none ${node === null || node === "champion" ? "gold-num" : "num font-bold text-fg"}`}>{pct(i.prob)}</p>
          {i.risk && (
            <div className="mt-4 border-t border-line pt-3">
              <p className="text-micro text-mute">{tt.risk} · {i.risk[0]}</p>
              <p className="num text-h3 font-semibold text-red">{pct(i.risk[1])}</p>
            </div>
          )}
          {i.notes.map((n) => <p key={n} className="mt-3 border-t border-line pt-3 text-caption text-mute">{n}</p>)}
        </motion.div>
      </AnimatePresence>
    </aside>
  );
}

function KnockoutPaths({ sim, locale }: { sim: SimTeam; locale: Locale }) {
  const tt = dict(locale).tournament;
  const rows: { title: string; steps: [string, number][] }[] = [
    { title: tt.upperPath, steps: [[tt.upperSemi, sim.p_upper_semifinal], [tt.upperFinal, sim.p_upper_final], [tt.upperFinalWin, sim.p_upper_final_win]] },
    { title: tt.lowerPath, steps: [[tt.dropLower, sim.p_drop_to_lower], [tt.lowerFinal, sim.p_lower_final]] },
  ];
  return (
    <Panel>
      <PanelTitle title={tt.paths} sub="BO7" />
      <div className="space-y-6">
        {rows.map((r) => (
          <div key={r.title}>
            <p className="text-caption font-semibold text-gold">{r.title}</p>
            <div className="mt-2 grid gap-2" style={{ gridTemplateColumns: `repeat(${r.steps.length}, minmax(0,1fr))` }}>
              {r.steps.map(([label, v]) => (
                <div key={label} className="rounded-xl bg-ink-850/80 px-4 py-3">
                  <p className="text-caption text-mute">{label}</p>
                  <p className="num mt-1 text-h2 font-semibold">{pct(v)}</p>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </Panel>
  );
}

