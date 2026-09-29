import Image from "next/image";
import Link from "next/link";
import { teamsByChampion } from "@/lib/data";
import { teamAssets } from "@/lib/assets";
import { pct } from "@/lib/format";
import { dict, href, teamName, type Locale } from "@/lib/i18n";
import { presentation } from "@/data/teamPresentation";
import { TeamLogo } from "@/components/common/ui";

export function HomeView({ locale }: { locale: Locale }) {
  const t = dict(locale);
  const h = t.home;
  const [leader, ...rest] = teamsByChampion;
  const name = (id: string) => { const p = presentation(id); return teamName(locale, p.displayNameZh, p.displayNameEn); };
  const photo = teamAssets(leader.id)?.teamPhoto;
  const maxP = leader.championship_probability;

  return (
    <div className="mx-auto w-full max-w-standard overflow-x-clip px-5 pb-20 pt-6 md:px-8 md:pt-10">
      {/* Favourite */}
      <section className="panel relative isolate overflow-hidden">
        {photo && (
          <div className="absolute inset-y-0 right-0 -z-10 w-full md:w-[68%]">
            <Image src={photo} alt="" fill priority sizes="(min-width: 768px) 800px, 100vw" className="object-cover object-center opacity-60" />
            <div className="absolute inset-0 bg-gradient-to-r from-ink-950 via-ink-950/70 to-transparent" />
            <div className="absolute inset-0 bg-gradient-to-t from-ink-950 via-transparent to-transparent" />
          </div>
        )}
        <div className="flex min-h-[420px] flex-col justify-end p-6 md:min-h-[480px] md:p-12">
          <p className="kicker">{h.kicker}</p>
          <div className="mt-6 flex items-center gap-5">
            <TeamLogo id={leader.id} size={104} priority className="drop-shadow-[0_0_24px_rgba(217,179,106,0.45)]" />
            <div>
              <p className="text-caption font-medium text-gold-soft">{h.favourite} · {t.groups[leader.group]} · {t.seed(leader.seed)}</p>
              <h1 className="mt-1 text-display font-bold text-fg">{name(leader.id)}</h1>
            </div>
          </div>
          <p className="mt-8 text-caption text-mute">{t.common.champion}</p>
          <p className="gold-num text-mega leading-none">{pct(leader.championship_probability)}</p>
        </div>
      </section>

      {/* Contenders 2–5 */}
      <section className="mt-10">
        <h2 className="kicker">{h.challengers}</h2>
        <ol className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
          {rest.slice(0, 4).map((tm, i) => (
            <li key={tm.id}>
              <Link href={href(locale, `/teams/${tm.id}`)} className="panel group flex h-full items-center gap-4 p-4 transition-colors hover:border-gold md:p-5">
                <TeamLogo id={tm.id} size={60} className="transition-transform group-hover:scale-105" />
                <div className="min-w-0">
                  <p className="text-caption text-faint">#{i + 2}</p>
                  <p className="truncate text-body font-semibold text-fg">{name(tm.id)}</p>
                  <p className="gold-num text-h1 leading-tight">{pct(tm.championship_probability)}</p>
                </div>
              </Link>
            </li>
          ))}
        </ol>
      </section>

      {/* The field */}
      <section className="panel mt-10 p-6 md:p-10">
        <div className="flex flex-wrap items-end justify-between gap-2">
          <h2 className="text-h2 font-semibold">{h.field}</h2>
          <p className="text-caption text-mute">{h.fieldSub}</p>
        </div>
        <div className="gold-rule mt-6" />
        <ol className="mt-8 grid grid-cols-3 items-end gap-x-3 gap-y-8 sm:grid-cols-4 lg:grid-cols-12">
          {teamsByChampion.map((tm) => {
            const size = Math.round(40 + 56 * Math.sqrt(tm.championship_probability / maxP));
            return (
              <li key={tm.id}>
                <Link href={href(locale, `/teams/${tm.id}`)} className="group flex flex-col items-center text-center">
                  <span className="flex h-24 items-end">
                    <TeamLogo id={tm.id} size={size} priority={tm.id === leader.id} className="opacity-90 transition group-hover:scale-110 group-hover:opacity-100" />
                  </span>
                  <span className={`num mt-3 text-body font-semibold ${tm.id === leader.id ? "text-gold-soft" : "text-fg"}`}>{pct(tm.championship_probability)}</span>
                  <span className="mt-0.5 w-full truncate text-micro text-mute">{teamName(locale, presentation(tm.id).shortName, presentation(tm.id).displayNameEn)}</span>
                </Link>
              </li>
            );
          })}
        </ol>
      </section>

      {/* Explore */}
      <section className="mt-10 grid gap-3 md:grid-cols-3">
        {h.explore.map(([title, sub, path]) => (
          <Link key={path} href={href(locale, path)} className="panel group p-5 transition-colors hover:border-gold">
            <p className="text-h3 font-semibold text-fg">{title} <span className="text-gold transition-transform group-hover:translate-x-1">→</span></p>
            <p className="mt-1 text-caption text-mute">{sub}</p>
          </Link>
        ))}
      </section>
    </div>
  );
}
