import type { Locale } from "@/lib/i18n";
import { TacticalMap } from "@/components/map/TacticalMap";

export function TeamTactical({ locale }: { locale: Locale; teamId?: string }) {
  return <TacticalMap locale={locale} />;
}
