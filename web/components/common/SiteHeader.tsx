"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { dict, href, type Locale } from "@/lib/i18n";
import { Signature } from "./ui";

const NAV = [
  { key: "home", path: "" },
  { key: "tournament", path: "/tournament" },
  { key: "teams", path: "/teams" },
  { key: "methodology", path: "/methodology" },
] as const;

export function SiteHeader({ locale }: { locale: Locale }) {
  const t = dict(locale);
  const pathname = usePathname() ?? `/${locale}`;
  const rest = pathname.replace(/^\/(zh|en)/, "");
  const active = (p: string) => (p === "" ? rest === "" : rest.startsWith(p));

  return (
    <header className="sticky top-0 z-40 border-b border-line bg-navy/90 backdrop-blur-md">
      <div className="mx-auto flex max-w-standard flex-wrap items-center gap-x-6 px-5 md:h-16 md:flex-nowrap md:px-8">
        <Link href={href(locale)} className="mr-auto shrink-0 py-2.5 leading-tight md:mr-0 md:py-0">
          <span className="block text-[11px] font-semibold tracking-[0.2em] text-gold">KPL 2026</span>
          <span className="block whitespace-nowrap text-[15px] font-semibold text-fg">{t.brand}</span>
        </Link>
        <nav className="order-last -mx-3 flex w-[calc(100%+1.5rem)] min-w-0 items-center gap-1 overflow-x-auto border-t border-line [scrollbar-width:none] md:order-none md:mx-0 md:w-auto md:flex-1 md:justify-center md:border-0">
          {NAV.map((n) => {
            const on = active(n.path);
            return (
              <Link key={n.key} href={href(locale, n.path)}
                className={`relative whitespace-nowrap px-3.5 py-2.5 text-[15px] transition-colors ${on ? "font-semibold text-gold-soft" : "text-mute hover:text-fg"}`}>
                {t.nav[n.key]}
                {on && <span className="absolute inset-x-3 bottom-0 h-0.5 rounded-full bg-gradient-to-r from-transparent via-gold to-transparent" />}
              </Link>
            );
          })}
        </nav>
        <div className="flex shrink-0 items-center text-[13px]" aria-label="language">
          <Link href={`/zh${rest}`} className={locale === "zh" ? "text-fg" : "text-faint hover:text-fg"} lang="zh-CN">中文</Link>
          <span className="px-1.5 text-faint">|</span>
          <Link href={`/en${rest}`} className={locale === "en" ? "text-fg" : "text-faint hover:text-fg"} lang="en">EN</Link>
        </div>
        <div className="hidden shrink-0 md:block">
          <Signature />
        </div>
      </div>
    </header>
  );
}
