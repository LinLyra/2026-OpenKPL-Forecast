"use client";

import { teamsByChampion } from "@/lib/data";
import { dict, teamName, type Locale } from "@/lib/i18n";
import { presentation } from "@/data/teamPresentation";
import { TeamLogo } from "./ui";

/** Native select of all 12 teams (ordered by title odds) showing the current team's logo. */
export function TeamSelect({ locale, value, onChange, label, disabledId, className = "" }: {
  locale: Locale; value: string; onChange: (id: string) => void; label: string; disabledId?: string; className?: string;
}) {
  const t = dict(locale);
  return (
    <label className={`relative flex min-w-0 items-center gap-2 rounded-full border border-line-strong bg-ink-900/80 py-1.5 pl-2 pr-9 transition-colors focus-within:border-gold hover:border-gold ${className}`}>
      <span className="sr-only">{label}</span>
      <TeamLogo id={value} size={28} />
      <select value={value} onChange={(e) => onChange(e.target.value)}
        className="min-w-0 flex-1 cursor-pointer appearance-none truncate bg-transparent text-body font-medium text-fg focus:outline-none [&>option]:bg-ink-900">
        {teamsByChampion.map((tm) => {
          const p = presentation(tm.id);
          return (
            <option key={tm.id} value={tm.id} disabled={tm.id === disabledId}>
              {teamName(locale, p.displayNameZh, p.displayNameEn)} · {t.groups[tm.group]}
            </option>
          );
        })}
      </select>
      <svg aria-hidden width="12" height="12" viewBox="0 0 12 12" className="pointer-events-none absolute right-4 text-gold">
        <path d="M2.5 4.5 L6 8 L9.5 4.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    </label>
  );
}
