import { dict, type Locale } from "@/lib/i18n";
import { Signature } from "./ui";

export function SiteFooter({ locale }: { locale: Locale }) {
  const t = dict(locale);
  return (
    <footer className="mt-10 border-t border-line bg-navy/60">
      <div className="mx-auto flex max-w-standard flex-col gap-2 px-5 py-7 text-caption text-mute md:flex-row md:items-center md:justify-between md:px-8">
        <p className="flex items-center gap-2">{t.footer.project} · <Signature size="sm" /></p>
        <p className="text-faint">{t.footer.disclaimer}</p>
      </div>
    </footer>
  );
}
