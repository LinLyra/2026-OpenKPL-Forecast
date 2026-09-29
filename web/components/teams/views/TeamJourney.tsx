import type { Locale } from "@/lib/i18n";
import { TournamentJourney } from "@/components/tournament/TournamentJourney";

export function TeamJourney({ locale, teamId }: { locale: Locale; teamId: string }) {
  return <TournamentJourney key={teamId} locale={locale} initialTeam={teamId} showSelector={false} />;
}
