import Link from "next/link";
import { teamsByChampion } from "@/lib/data";
import { pct, rating } from "@/lib/format";
import { dict, href, teamName, type Locale } from "@/lib/i18n";
import { presentation } from "@/data/teamPresentation";
import { Page, PageHeader, TeamLogo } from "@/components/common/ui";

export function TeamsView({ locale }: { locale: Locale }) {
  const t = dict(locale);
  return (
    <Page>
      <PageHeader kicker={t.teams.kicker} title={t.teams.title} lead={t.teams.lead} />
      {(["MASTER", "ELITE"] as const).map((g) => (
        <section key={g} className="mt-12">
          <h2 className="kicker">{t.groups[g]}</h2>
          <ul className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
            {teamsByChampion.filter((tm) => tm.group === g).sort((a, b) => (a.seed ?? 99) - (b.seed ?? 99)).map((tm) => {
              const p = presentation(tm.id);
              return (
                <li key={tm.id}>
                  <Link href={href(locale, `/teams/${tm.id}`)} className="panel group flex h-full flex-col items-center px-4 py-6 text-center transition-colors hover:border-gold">
                    <TeamLogo id={tm.id} size={88} priority={g === "MASTER"} className="transition-transform group-hover:scale-105" />
                    <p className="mt-4 text-body font-semibold">{teamName(locale, p.displayNameZh, p.displayNameEn)}</p>
                    <p className="text-micro text-faint">{t.seed(tm.seed)} · {t.common.rating} {rating(tm.frozen_b5_rating)}</p>
                    <p className="gold-num mt-3 text-h1 leading-none">{pct(tm.championship_probability)}</p>
                    <p className="mt-1 text-micro text-mute">{t.common.champion}</p>
                  </Link>
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </Page>
  );
}
