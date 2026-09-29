import type { ReactNode } from "react";
import type { Locale } from "@/lib/i18n";
import { SiteHeader } from "./SiteHeader";
import { SiteFooter } from "./SiteFooter";

export function SiteShell({ locale, children }: { locale: Locale; children: ReactNode }) {
  return (
    <div className="relative z-10 flex min-h-screen flex-col">
      <SiteHeader locale={locale} />
      <main className="flex-1">{children}</main>
      <SiteFooter locale={locale} />
    </div>
  );
}
