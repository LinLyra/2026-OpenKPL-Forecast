"use client";

import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";
import { getTeam, matchups, seriesProbability } from "@/lib/data";
import { mmdd, pct, rating } from "@/lib/format";
import { dict, href, teamName, type Locale } from "@/lib/i18n";
import { presentation } from "@/data/teamPresentation";
import { TeamSelect } from "@/components/common/TeamSelect";
import { TeamLogo } from "@/components/common/ui";

export function MatchupView({ locale }: { locale: Locale }) {
  const t = dict(locale);
  const m = t.matchup;
  const [a, setA] = useState("wolves");
  const [b, setB] = useState("ttg");
  const pA = seriesProbability(a, b)!;
  const pB = seriesProbability(b, a)!;
  const A = getTeam(a)!, B = getTeam(b)!;
  const meet = matchups.data.stage1_ledger.find(
    (r) => (r.team_a_id === a && r.team_b_id === b) || (r.team_a_id === b && r.team_b_id === a),
  );
  const gap = A.frozen_b5_rating - B.frozen_b5_rating;

  return (
    <div className="mx-auto w-full max-w-standard px-5 pb-20 pt-10 md:px-8 md:pt-14">
      <header className="text-center">
        <p className="kicker">{m.kicker}</p>
        <h1 className="mt-3 text-h1 font-semibold">{m.title}</h1>
      </header>

      <section className="panel relative isolate mt-10 overflow-hidden px-5 pb-10 pt-8 md:px-12 md:pb-14">
        <div aria-hidden className="absolute inset-y-0 left-0 -z-10 w-1/2 bg-[radial-gradient(ellipse_at_20%_50%,rgba(74,155,255,0.22),transparent_65%)]" />
        <div aria-hidden className="absolute inset-y-0 right-0 -z-10 w-1/2 bg-[radial-gradient(ellipse_at_80%_50%,rgba(255,80,100,0.2),transparent_65%)]" />

        <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3 md:gap-8">
          <TeamSelect locale={locale} value={a} onChange={setA} label={m.teamA} disabledId={b} />
          <button type="button" onClick={() => { setA(b); setB(a); }}
            className="rounded-full border border-line-strong px-4 py-2 text-caption font-semibold text-gold-soft transition-colors hover:border-gold">
            ⇄ {m.swap}
          </button>
          <TeamSelect locale={locale} value={b} onChange={setB} label={m.teamB} disabledId={a} />
        </div>

        <div className="mt-10 grid grid-cols-[1fr_auto_1fr] items-center gap-2 md:gap-8">
          <Side locale={locale} id={a} p={pA} align="left" />
          <span className="font-[family-name:var(--font-display)] text-[2rem] font-black italic tracking-tight text-gold md:text-[4.5rem]"
            style={{ textShadow: "0 0 32px rgba(217,179,106,0.45)" }}>VS</span>
          <Side locale={locale} id={b} p={pB} align="right" />
        </div>

        <div className="mt-10 flex h-2 overflow-hidden rounded-full">
          <motion.span className="h-full bg-gradient-to-r from-blue/40 to-blue" initial={false} animate={{ width: `${pA * 100}%` }} transition={{ duration: 0.6 }} />
          <span className="w-1 bg-ink-950" />
          <motion.span className="h-full flex-1 bg-gradient-to-r from-red to-red/40" />
        </div>
        <p className="mt-3 text-center text-micro text-faint">{m.series} · {m.formatNote}</p>
      </section>

      <section className="mt-6 grid gap-3 sm:grid-cols-3">
        <div className="panel p-5">
          <p className="text-caption text-mute">{t.common.rating}</p>
          <p className="num mt-1 text-h2 font-semibold"><span className="text-blue">{rating(A.frozen_b5_rating)}</span><span className="px-2 text-faint">:</span><span className="text-red">{rating(B.frozen_b5_rating)}</span></p>
        </div>
        <div className="panel p-5">
          <p className="text-caption text-mute">{m.ratingGap}</p>
          <p className="num mt-1 text-h2 font-semibold">{gap > 0 ? "+" : ""}{gap.toFixed(0)}</p>
        </div>
        <div className="panel p-5">
          <p className="text-caption text-mute">{m.meeting}</p>
          {meet
            ? <p className="num mt-1 text-h2 font-semibold">{mmdd(meet.scheduled_date)} <span className="text-body font-normal text-mute">{meet.format}</span></p>
            : <p className="mt-1.5 text-caption text-mute">{A.group === B.group ? m.sameGroup : "—"}</p>}
        </div>
      </section>
    </div>
  );
}

function Side({ locale, id, p, align }: { locale: Locale; id: string; p: number; align: "left" | "right" }) {
  const pr = presentation(id);
  const color = align === "left" ? "text-blue" : "text-red";
  return (
    <div className={`flex min-w-0 flex-col items-center text-center`}>
      <Link href={href(locale, `/teams/${id}`)} className="group flex flex-col items-center">
        <AnimatePresence mode="wait">
          <motion.span key={id} initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.25 }}
            className="flex h-24 w-24 items-center justify-center md:h-44 md:w-44">
            <TeamLogo id={id} size={176} priority className="h-full! w-full! drop-shadow-[0_10px_40px_rgba(0,0,0,0.6)] transition-transform group-hover:scale-105" />
          </motion.span>
        </AnimatePresence>
        <span className="mt-3 max-w-full truncate text-body font-semibold md:text-h2">{teamName(locale, pr.displayNameZh, pr.displayNameEn)}</span>
      </Link>
      <p className={`display-num num mt-3 text-[2.25rem] font-bold leading-none md:text-display ${color}`}>{pct(p)}</p>
    </div>
  );
}
