import Link from "next/link";
import type { ReactNode } from "react";
import { getTeam, teamsByChampion } from "@/lib/data";
import { teamAssets } from "@/lib/assets";
import { pct, rating } from "@/lib/format";
import { dict, href, teamName, type Locale } from "@/lib/i18n";
import { presentation } from "@/data/teamPresentation";
import { TeamLogo } from "@/components/common/ui";
import { TeamHeader } from "./TeamHeader";
import { TeamTabs } from "./TeamTabs";

export function TeamShell({ locale, teamId, children }: { locale: Locale; teamId: string; children: ReactNode }) {
  const t = dict(locale);
  const team = getTeam(teamId)!;
  const p = presentation(teamId);
  const a = teamAssets(teamId);
  const rank = teamsByChampion.findIndex((x) => x.id === teamId) + 1;

  return (
    <div className="mx-auto w-full max-w-standard px-5 pb-20 pt-6 md:px-8 md:pt-8">
      <nav aria-label={t.nav.teams} className="-mx-1 overflow-x-auto [scrollbar-width:none]">
        <ul className="flex min-w-max gap-1.5 px-1">
          {teamsByChampion.map((tm) => {
            const on = tm.id === teamId;
            return (
              <li key={tm.id}>
                <Link href={href(locale, `/teams/${tm.id}`)} aria-current={on ? "page" : undefined}
                  title={teamName(locale, presentation(tm.id).displayNameZh, presentation(tm.id).displayNameEn)}
                  className={`flex h-12 w-12 items-center justify-center rounded-xl border transition ${on ? "border-gold bg-gold/10" : "border-transparent opacity-55 hover:opacity-100"}`}>
                  <TeamLogo id={tm.id} size={34} />
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      <TeamHeader
        locale={locale}
        teamId={teamId}
        name={teamName(locale, p.displayNameZh, p.displayNameEn)}
        meta={`${p.city ? `${p.city} · ` : ""}${t.groups[team.group]} · ${t.seed(team.seed)}`}
        rank={t.profile.rank(rank)}
        slogan={locale === "zh" ? a?.slogan ?? null : null}
        photo={a?.teamHeroImage ?? a?.teamPhoto ?? null}
        stats={[
          [t.common.champion, pct(team.championship_probability)],
          [t.common.final, pct(team.final_probability)],
          [t.common.direct, pct(team.direct_knockout_probability)],
          [t.common.rating, rating(team.frozen_b5_rating)],
        ]}
      />

      <div className="mt-2 border-b border-line">
        <TeamTabs locale={locale} teamId={teamId} />
      </div>
      <div className="mt-8">{children}</div>
    </div>
  );
}
