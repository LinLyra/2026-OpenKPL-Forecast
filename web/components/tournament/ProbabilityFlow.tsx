"use client";

import { motion } from "framer-motion";
import type { SimTeam } from "@/lib/types";
import { pct } from "@/lib/format";
import { dict, type Locale } from "@/lib/i18n";
import { NODE_W, StageNode } from "./StageNode";

export type FlowNodeId = "stage1" | "direct" | "breakthrough" | "out_s1" | "out_bt" | "knockout" | "out_ko" | "final" | "runner" | "champion";

const W = 1200, H = 470, SCALE = 150, RISK = "#ff5064";

interface NodeSpec { id: FlowNodeId; x: number; cy: number; value: number; terminal?: boolean; labelSide?: "top" | "right" }

/**
 * Every value is a stored frozen probability from tournament.json: milestones from PRIMARY_FORECAST.csv and
 * terminal branches from knockout_forecast.csv p_terminal_* (knockout exit = sum of the four lower-bracket exits).
 */
export function flowModel(s: SimTeam) {
  const tm = s.terminal;
  const outKo = tm.LB_R1 + tm.LB_R2 + tm.LB_SF + tm.LB_F;
  const nodes: NodeSpec[] = [
    { id: "stage1", x: 40, cy: 225, value: 1 },
    { id: "direct", x: 330, cy: 125, value: s.p_direct_knockout },
    { id: "breakthrough", x: 330, cy: 305, value: s.p_breakthrough },
    { id: "out_s1", x: 330, cy: 430, value: tm.STAGE1, terminal: true, labelSide: "right" },
    { id: "out_bt", x: 560, cy: 430, value: tm.BREAKTHROUGH, terminal: true, labelSide: "right" },
    { id: "knockout", x: 640, cy: 190, value: s.p_knockout },
    { id: "out_ko", x: 860, cy: 430, value: outKo, terminal: true, labelSide: "right" },
    { id: "final", x: 900, cy: 190, value: s.p_final },
    { id: "runner", x: 1080, cy: 360, value: tm.FINAL, terminal: true, labelSide: "right" },
    { id: "champion", x: 1080, cy: 190, value: s.p_champion },
  ];
  const links: [FlowNodeId, FlowNodeId, number][] = [
    ["stage1", "direct", s.p_direct_knockout],
    ["stage1", "breakthrough", s.p_breakthrough],
    ["stage1", "out_s1", tm.STAGE1],
    ["direct", "knockout", s.p_direct_knockout],
    ["breakthrough", "knockout", s.p_breakthrough_win],
    ["breakthrough", "out_bt", tm.BREAKTHROUGH],
    ["knockout", "final", s.p_final],
    ["knockout", "out_ko", outKo],
    ["final", "champion", s.p_champion],
    ["final", "runner", tm.FINAL],
  ];
  return { nodes, links };
}

function ribbon(x0: number, a0: number, b0: number, x1: number, a1: number, b1: number) {
  const xm = (x0 + x1) / 2;
  const f = (n: number) => n.toFixed(2);
  return `M${f(x0)} ${f(a0)} C${f(xm)} ${f(a0)} ${f(xm)} ${f(a1)} ${f(x1)} ${f(a1)} L${f(x1)} ${f(b1)} C${f(xm)} ${f(b1)} ${f(xm)} ${f(b0)} ${f(x0)} ${f(b0)} Z`;
}

export function ProbabilityFlow({
  sim, locale, hovered, onHover,
}: { sim: SimTeam; locale: Locale; hovered: FlowNodeId | null; onHover: (id: FlowNodeId | null) => void }) {
  const t = dict(locale);
  const color = "#d9b36a";
  const { nodes, links } = flowModel(sim);
  const byId = Object.fromEntries(nodes.map((n) => [n.id, n])) as Record<FlowNodeId, NodeSpec>;
  const top = (n: NodeSpec) => n.cy - (n.value * SCALE) / 2;
  const outOff: Partial<Record<FlowNodeId, number>> = {};
  const inOff: Partial<Record<FlowNodeId, number>> = {};

  const labels: Record<FlowNodeId, string> = {
    stage1: t.stages.stage1,
    direct: t.stages.direct,
    breakthrough: t.stages.breakthrough,
    out_s1: `${t.stages.stage1} · ${t.stages.eliminated}`,
    out_bt: `${t.stages.breakthrough} · ${t.stages.eliminated}`,
    knockout: t.stages.knockout,
    out_ko: `${t.stages.knockout} · ${t.stages.eliminated}`,
    final: t.stages.final,
    runner: t.stages.runnerUp,
    champion: t.stages.champion,
  };

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full min-w-[760px]" role="img" aria-label={t.tournament.flow}>
      <defs>
        <linearGradient id="flow-risk" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor={RISK} stopOpacity="0.08" />
          <stop offset="1" stopColor={RISK} stopOpacity="0.3" />
        </linearGradient>
      </defs>
      <line x1="0" x2={W} y1="398" y2="398" stroke="rgba(255,80,100,0.3)" strokeDasharray="2 6" />
      <text x="0" y="388" fontSize="16" style={{ fill: "rgba(255,80,100,0.8)" }}>{t.stages.eliminated}</text>

      {links.map(([a, b, v]) => {
        const na = byId[a], nb = byId[b];
        const oa = outOff[a] ?? 0, ib = inOff[b] ?? 0;
        outOff[a] = oa + v * SCALE;
        inOff[b] = ib + v * SCALE;
        const y0 = top(na) + oa, y1 = top(nb) + ib;
        const d = ribbon(na.x + NODE_W, y0, y0 + v * SCALE, nb.x, y1, y1 + v * SCALE);
        const risk = !!nb.terminal;
        const lit = hovered === null || hovered === a || hovered === b;
        return (
          <motion.path
            key={`${a}-${b}`}
            initial={{ d, opacity: 0 }}
            animate={{ d, opacity: lit ? 1 : 0.25 }}
            transition={{ duration: 0.65, ease: [0.3, 0.6, 0.2, 1] }}
            fill={risk ? "url(#flow-risk)" : color}
            fillOpacity={risk ? 1 : 0.22}
            stroke={risk ? RISK : color}
            strokeOpacity={risk ? 0.35 : 0.45}
            strokeWidth={0.6}
          />
        );
      })}

      {nodes.map((n) => (
        <StageNode
          key={n.id}
          id={n.id}
          x={n.x}
          top={top(n)}
          height={n.value * SCALE}
          label={labels[n.id]}
          value={pct(n.value)}
          color={n.terminal ? RISK : n.id === "champion" ? "#f3dca4" : color}
          active={hovered === n.id}
          terminal={n.terminal}
          labelSide={n.labelSide}
          onHover={(id) => onHover(id as FlowNodeId | null)}
        />
      ))}
    </svg>
  );
}
