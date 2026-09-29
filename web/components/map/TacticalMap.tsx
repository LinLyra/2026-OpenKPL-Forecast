"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import { POSITIONS, type Position } from "@/data/teamPresentation";
import { FOCUS, HEAT, OBJECTIVES, ROLE_COLOR, ROLE_ZONE, ROUTES, STATES, frameAt, type TacticalState } from "@/data/map/tactical";
import { REFERENCE, VIEW_H, VIEW_W, toView, type TrackingFrame, type TrackingSource } from "@/lib/mapProjection";
import { dict, type Locale } from "@/lib/i18n";
import { TrackingLayer } from "./TrackingLayer";

type Layer = "heat" | "paths" | "objectives";
const line = (pts: [number, number][]) => pts.map((p) => toView({ x: p[0], y: p[1] }).map((v) => v.toFixed(1)).join(",")).join(" ");

/**
 * Tactical board on the real Canyon of Kings top-down map. Without `observed` frames it plays the
 * hand-authored illustration and says so once; with observed frames it renders them as tracking.
 */
export function TacticalMap({ locale, observed, portraits }: {
  locale: Locale;
  observed?: TrackingFrame[];
  portraits?: Record<string, string>;
}) {
  const t = dict(locale).tactical;
  const source: TrackingSource = observed?.length ? "observed" : "illustration";
  const [time, setTime] = useState(1);
  const [role, setRole] = useState<Position | null>(null);
  const [layers, setLayers] = useState<Record<Layer, boolean>>({ heat: true, paths: true, objectives: true });
  const [playing, setPlaying] = useState(false);
  const raf = useRef<number>(0);

  const tween = (to: number, ms: number, onDone?: () => void) => {
    cancelAnimationFrame(raf.current);
    const from = time, start = performance.now();
    const step = (now: number) => {
      const f = Math.min(1, (now - start) / ms);
      const e = f < 0.5 ? 2 * f * f : 1 - (-2 * f + 2) ** 2 / 2;
      setTime(from + (to - from) * e);
      if (f < 1) raf.current = requestAnimationFrame(step);
      else onDone?.();
    };
    raf.current = requestAnimationFrame(step);
  };
  useEffect(() => () => cancelAnimationFrame(raf.current), []);

  const play = () => {
    if (playing) { cancelAnimationFrame(raf.current); setPlaying(false); return; }
    setPlaying(true);
    const from = time >= 2.99 ? 0 : time;
    if (from === 0) setTime(0);
    const start = performance.now(), ms = (3 - from) * 2600;
    const step = (now: number) => {
      const f = Math.min(1, (now - start) / ms);
      setTime(from + (3 - from) * f);
      if (f < 1) raf.current = requestAnimationFrame(step);
      else setPlaying(false);
    };
    raf.current = requestAnimationFrame(step);
  };

  const k = Math.min(3, Math.max(0, Math.round(time)));
  const routeIdx = Math.max(1, Math.ceil(time));
  const state: TacticalState | null = k === 0 ? null : STATES[k - 1];
  const points = source === "observed"
    ? observed![Math.min(observed!.length - 1, Math.floor((time / 3) * observed!.length))].points
    : frameAt(time);
  const heat = HEAT[k];

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_260px] lg:items-start">
      <div className="mx-auto w-full min-w-0" style={{ maxWidth: `calc((100svh - 150px) * ${REFERENCE.width / REFERENCE.height})` }}>
        <div className="relative overflow-hidden rounded-2xl border border-line-strong shadow-[0_30px_80px_-30px_rgba(0,0,0,0.8)]"
          style={{ aspectRatio: `${REFERENCE.width} / ${REFERENCE.height}` }}>
          <Image src={REFERENCE.image} alt={locale === "zh" ? "王者峡谷顶视图" : "Canyon of Kings top-down map"} fill priority
            sizes="(min-width: 1024px) 960px, 100vw" className="object-cover" />
          <svg viewBox={`0 0 ${VIEW_W} ${VIEW_H.toFixed(2)}`} className="absolute inset-0 h-full w-full">
            <defs>
              <radialGradient id="heat">
                <stop offset="0" stopColor="#ffcf6b" stopOpacity="0.75" />
                <stop offset="0.5" stopColor="#ff8a3d" stopOpacity="0.3" />
                <stop offset="1" stopColor="#ff5a3d" stopOpacity="0" />
              </radialGradient>
              <mask id="zone-mask">
                <rect width={VIEW_W} height={VIEW_H} fill="white" />
                {role && <polyline points={line(ROLE_ZONE[role])} fill="none" stroke="black" strokeWidth={96} strokeLinecap="round" strokeLinejoin="round" />}
              </mask>
            </defs>

            <rect width={VIEW_W} height={VIEW_H} fill="#04070e" mask="url(#zone-mask)"
              style={{ opacity: role ? 0.55 : 0.08, transition: "opacity 400ms" }} />
            {role && (
              <polyline points={line(ROLE_ZONE[role])} fill="none" stroke={ROLE_COLOR[role]} strokeOpacity={0.09} strokeWidth={96}
                strokeLinecap="round" strokeLinejoin="round" style={{ animation: "fadein 400ms ease" }} />
            )}

            {layers.heat && (
              <g key={k} style={{ mixBlendMode: "screen", animation: "fadein 600ms ease" }}>
                {heat.map(([x, y, r, a], i) => (
                  <circle key={i} cx={x * VIEW_W} cy={y * VIEW_H} r={r * VIEW_W} fill="url(#heat)" opacity={a * 0.8} />
                ))}
              </g>
            )}

            {layers.objectives && OBJECTIVES.map((o) => {
              const [x, y] = toView(o);
              const focus = FOCUS[k] === o.id;
              const big = o.kind !== "buff";
              const label = o.kind === "overlord" ? t.overlord : o.kind === "tyrant" ? t.tyrant : "BUFF";
              return (
                <g key={o.id} transform={`translate(${x.toFixed(1)} ${y.toFixed(1)})`}>
                  {focus && <circle r={46} fill="none" stroke="#f3dca4" strokeWidth={2} opacity={0.8}>
                    <animate attributeName="r" values="34;52;34" dur="2.4s" repeatCount="indefinite" />
                    <animate attributeName="opacity" values="0.9;0.2;0.9" dur="2.4s" repeatCount="indefinite" />
                  </circle>}
                  <circle r={big ? 26 : 14} fill="none" stroke={focus ? "#f3dca4" : "rgba(243,220,164,0.7)"} strokeWidth={big ? 2.5 : 1.8} />
                  {big && (
                    <text y={-34} textAnchor="middle" fontSize={17} fontWeight={700} fill="#f3dca4" stroke="#04070e" strokeWidth={4} paintOrder="stroke">{label}</text>
                  )}
                </g>
              );
            })}

            {layers.paths && source === "illustration" && time > 0.02 && (POSITIONS.filter((r) => !role || r === role)).map((r) => {
              const route = ROUTES[routeIdx][r];
              if (route.length < 2) return null;
              return (
                <polyline key={`${r}-${routeIdx}`} points={line(route)} fill="none" stroke={ROLE_COLOR[r]}
                  strokeWidth={role ? 5 : 3} strokeOpacity={role ? 0.95 : 0.6} strokeDasharray="10 9" strokeLinecap="round">
                  <animate attributeName="stroke-dashoffset" from="38" to="0" dur="1s" repeatCount="indefinite" />
                </polyline>
              );
            })}

            <TrackingLayer points={points} locale={locale} focus={role} portraits={portraits} />
          </svg>

          {source === "illustration" && (
            <span className="absolute left-3 top-3 rounded-full bg-navy/75 px-3 py-1 text-micro text-gold-soft backdrop-blur">{t.label}</span>
          )}
          <span className="absolute bottom-3 left-3 rounded-full bg-blue/20 px-2.5 py-0.5 text-micro font-semibold text-blue">{t.blue}</span>
          <span className="absolute right-3 top-3 rounded-full bg-red/20 px-2.5 py-0.5 text-micro font-semibold text-red">{t.red}</span>
        </div>

      </div>

      <aside className="space-y-6 lg:sticky lg:top-24">
        <div role="tablist" className="flex gap-1 rounded-xl border border-line bg-ink-900/70 p-1 lg:flex-col">
          {STATES.map((s, i) => (
            <button key={s} role="tab" aria-selected={state === s} type="button"
              onClick={() => { setPlaying(false); tween(i + 1, 1100); }}
              className={`flex-1 rounded-lg px-3 py-2.5 text-body font-semibold transition-colors ${state === s ? "bg-gradient-to-b from-gold-soft to-gold-deep text-navy" : "text-mute hover:text-fg"}`}>
              {t.states[s]}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-3">
          <button type="button" onClick={play} aria-label={playing ? t.pause : t.play}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-gradient-to-b from-gold-soft to-gold-deep text-navy">
            {playing
              ? <svg width="14" height="14" viewBox="0 0 14 14"><path d="M3 2h3v10H3zM8 2h3v10H8z" fill="currentColor" /></svg>
              : <svg width="14" height="14" viewBox="0 0 14 14"><path d="M3 1.5v11l9-5.5z" fill="currentColor" /></svg>}
          </button>
          <div className="min-w-0 flex-1">
            <input type="range" min={0} max={3} step={0.01} value={time} aria-label={t.play}
              onChange={(e) => { cancelAnimationFrame(raf.current); setPlaying(false); setTime(Number(e.target.value)); }}
              className="replay-range w-full" />
            <div className="mt-1.5 flex justify-between text-micro text-mute">
              {t.time.map((l, i) => <span key={l} className={k === i ? "text-gold-soft" : ""}>{l}</span>)}
            </div>
          </div>
        </div>
        <div>
          <div className="grid grid-cols-3 gap-2 lg:grid-cols-2">
            <button type="button" onClick={() => setRole(null)} aria-pressed={role === null}
              className={`rounded-lg border px-3 py-2.5 text-body font-semibold transition-colors ${role === null ? "border-gold bg-gold/10 text-gold-soft" : "border-line text-mute hover:text-fg"}`}>
              {t.all}
            </button>
            {POSITIONS.map((r) => (
              <button key={r} type="button" onClick={() => setRole(role === r ? null : r)} aria-pressed={role === r}
                className={`flex items-center gap-2 rounded-lg border px-3 py-2.5 text-body font-semibold transition-colors ${role === r ? "text-fg" : "border-line text-mute hover:text-fg"}`}
                style={role === r ? { borderColor: ROLE_COLOR[r], background: `${ROLE_COLOR[r]}1f` } : undefined}>
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: ROLE_COLOR[r] }} />
                {dict(locale).positions[r]}
              </button>
            ))}
          </div>
          <p className="mt-4 min-h-[4.5rem] text-caption leading-relaxed text-mute">
            {role ? t.roleNotes[role] : state ? t.stateNotes[state] : t.lead}
          </p>
        </div>
        <div className="flex flex-wrap gap-x-5 gap-y-2 border-t border-line pt-4">
          {(Object.keys(layers) as Layer[]).map((l) => (
            <label key={l} className="flex cursor-pointer items-center gap-2 text-caption text-mute">
              <input type="checkbox" checked={layers[l]} onChange={() => setLayers((s) => ({ ...s, [l]: !s[l] }))} className="accent-[#d9b36a]" />
              {t.layers[l]}
            </label>
          ))}
        </div>
      </aside>
    </div>
  );
}
