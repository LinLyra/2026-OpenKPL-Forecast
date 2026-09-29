"use client";

import Image from "next/image";
import { usePathname } from "next/navigation";
import type { Locale } from "@/lib/i18n";
import { TeamLogo } from "@/components/common/ui";

/** Full broadcast banner on the overview tab; a compact identity row on the other tabs. */
export function TeamHeader({ teamId, name, meta, rank, slogan, photo, stats }: {
  locale: Locale; teamId: string; name: string; meta: string; rank: string; slogan: string | null; photo: string | null;
  stats: [string, string][];
}) {
  const pathname = usePathname() ?? "";
  const overview = pathname.replace(/\/$/, "").endsWith(`/teams/${teamId}`);
  const [champion, ...rest] = stats;

  if (!overview) {
    return (
      <div className="mt-5 flex flex-wrap items-center gap-4">
        <TeamLogo id={teamId} size={52} />
        <div className="min-w-0 flex-1">
          <h1 className="text-h2 font-bold">{name}</h1>
          <p className="text-caption text-mute">{meta}</p>
        </div>
        <div className="text-right">
          <p className="text-micro text-mute">{champion[0]}</p>
          <p className="gold-num text-h1 leading-none">{champion[1]}</p>
        </div>
      </div>
    );
  }

  return (
    <section className="panel relative isolate mt-5 overflow-hidden">
      {photo && (
        <div className="absolute inset-y-0 right-0 -z-10 w-full md:w-[70%]">
          <Image src={photo} alt="" fill priority sizes="(min-width: 768px) 820px, 100vw" className="object-cover object-center opacity-70" />
          <div className="absolute inset-0 bg-gradient-to-r from-ink-950 via-ink-950/75 to-transparent" />
          <div className="absolute inset-0 bg-gradient-to-t from-ink-950/90 via-transparent to-transparent" />
        </div>
      )}
      <div className="flex min-h-[380px] flex-col justify-end p-6 md:min-h-[440px] md:p-10">
        <div className="flex items-center gap-5">
          <TeamLogo id={teamId} size={96} priority className="drop-shadow-[0_0_24px_rgba(217,179,106,0.4)]" />
          <div className="min-w-0">
            <p className="text-caption font-medium text-gold">{rank}</p>
            <h1 className="mt-1 text-display font-bold">{name}</h1>
            <p className="mt-1 text-caption text-mute">{meta}</p>
          </div>
        </div>
        {slogan && <p className="mt-5 text-h3 font-medium text-gold-soft">「{slogan}」</p>}
        <dl className="mt-8 flex flex-wrap items-end gap-x-10 gap-y-4">
          <div>
            <dt className="text-caption text-mute">{champion[0]}</dt>
            <dd className="gold-num text-display leading-none">{champion[1]}</dd>
          </div>
          {rest.map(([k, v]) => (
            <div key={k}>
              <dt className="text-caption text-mute">{k}</dt>
              <dd className="num text-h1 font-semibold leading-tight text-fg">{v}</dd>
            </div>
          ))}
        </dl>
      </div>
    </section>
  );
}
