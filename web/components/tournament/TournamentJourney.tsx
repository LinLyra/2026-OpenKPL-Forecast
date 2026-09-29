"use client";

import { AnimatePresence, motion } from "framer-motion";
import { Fragment, useState } from "react";
import { getSim, getStage1, teamsByChampion, tournament } from "@/lib/data";
import { mmdd, pct } from "@/lib/format";
import { dict, teamName, type Locale } from "@/lib/i18n";
import type { SimTeam, StageKey } from "@/lib/types";
import { presentation } from "@/data/teamPresentation";
import { Panel, PanelTitle, TeamLogo } from "@/components/common/ui";
import { ProbabilityFlow, type FlowNodeId } from "./ProbabilityFlow";

export function TournamentJourney({ locale, initialTeam = "wolves", showSelector = true }: { locale: Locale; initialTeam?: string; showSelector?: boolean }) {
  const t = dict(locale);
  const [teamId, setTeamId] = useState(initialTeam);
  const [hovered, setHovered] = useState<FlowNodeId | null>(null);
  const [selected, setSelected] = useState<FlowNodeId>("champion");
  const sim = getSim(teamId)!;
  const active = hovered ?? selected;

  return (
    <div className="space-y-6">
      {showSelector && <Structure locale={locale} />}

      <Panel>
        <PanelTitle title={t.tournament.flow} sub={t.tournament.flowSub} />
        {showSelector && <TeamPathSelector locale={locale} value={teamId} onChange={(id) => { setTeamId(id); setSelected("champion"); }} />}
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_15rem]">
          <div className="min-w-0 overflow-x-auto">
            <ProbabilityFlow sim={sim} locale={locale} active={active} onHover={setHovered} onSelect={setSelected} />
          </div>
          <StageDetail sim={sim} node={active} locale={locale} />
        </div>
      </Panel>
    </div>
  );
}

function TeamPathSelector({ locale, value, onChange }: { locale: Locale; value: string; onChange: (id: string) => void }) {
  const t = dict(locale);
  return (
    <div className="mb-6">
      <p className="sr-only">{t.tournament.select}</p>
      <div className="grid grid-cols-4 gap-2 sm:grid-cols-6 lg:grid-cols-12" role="group" aria-label={t.tournament.select}>
        {teamsByChampion.map((tm) => {
          const selected = tm.id === value;
          return (
            <button key={tm.id} type="button" onClick={() => onChange(tm.id)} aria-pressed={selected}
              aria-label={`${teamName(locale, presentation(tm.id).displayNameZh, presentation(tm.id).displayNameEn)} ${pct(tm.championship_probability)}`}
              className={`group flex min-h-20 flex-col items-center justify-center rounded-xl px-1 py-2 transition ${selected ? "bg-gold/12 ring-1 ring-gold/60" : "bg-ink-850/55 opacity-55 hover:opacity-100"}`}>
              <TeamLogo id={tm.id} size={34} className="transition-transform group-hover:scale-105" />
              <span className={`num mt-1 text-micro ${selected ? "text-gold-soft" : "text-mute"}`}>{pct(tm.championship_probability)}</span>
            </button>
          );
        })}
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
          {node === "knockout" && (
            <div className="mt-4 space-y-3 border-t border-line pt-3 text-caption">
              <div>
                <p className="font-semibold text-gold">{tt.upperPath}</p>
                <p className="mt-1 text-mute">{tt.upperSemi} <span className="num text-fg">{pct(sim.p_upper_semifinal)}</span> → {tt.upperFinal} <span className="num text-fg">{pct(sim.p_upper_final)}</span> → {tt.upperFinalWin} <span className="num text-fg">{pct(sim.p_upper_final_win)}</span></p>
              </div>
              <div>
                <p className="font-semibold text-gold">{tt.lowerPath}</p>
                <p className="mt-1 text-mute">{tt.dropLower} <span className="num text-fg">{pct(sim.p_drop_to_lower)}</span> → {tt.lowerFinal} <span className="num text-fg">{pct(sim.p_lower_final)}</span></p>
              </div>
            </div>
          )}
        </motion.div>
      </AnimatePresence>
    </aside>
  );
}
