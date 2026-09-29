"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { usePathname } from "next/navigation";
import { dict, href, type Locale } from "@/lib/i18n";

export const TEAM_VIEWS = ["overview", "journey"] as const;
export type TeamViewKey = (typeof TEAM_VIEWS)[number];

export function TeamTabs({ locale, teamId }: { locale: Locale; teamId: string }) {
  const t = dict(locale);
  const pathname = usePathname();
  const base = href(locale, `/teams/${teamId}`);
  const active: TeamViewKey = TEAM_VIEWS.find((v) => v !== "overview" && pathname.endsWith(`/${v}`)) ?? "overview";

  return (
    <nav className="-mx-1 overflow-x-auto [scrollbar-width:none]">
      <ul className="flex min-w-max gap-1">
        {TEAM_VIEWS.map((v) => {
          const on = v === active;
          return (
            <li key={v}>
              <Link href={v === "overview" ? base : `${base}/${v}`} aria-current={on ? "page" : undefined}
                className={`relative block px-4 py-3.5 text-body transition-colors ${on ? "font-semibold text-gold-soft" : "text-mute hover:text-fg"}`}>
                {t.teamTabs[v]}
                {on && <motion.span layoutId="team-tab" className="absolute inset-x-3 bottom-0 h-0.5 rounded-full bg-gold" transition={{ type: "spring", stiffness: 500, damping: 40 }} />}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
