import { dict, type Locale } from "@/lib/i18n";
import { Page, PageHeader } from "@/components/common/ui";
import { MatchupView } from "@/components/matchup/MatchupView";
import { TournamentJourney } from "./TournamentJourney";

export function TournamentView({ locale }: { locale: Locale }) {
  const t = dict(locale);
  return (
    <Page>
      <PageHeader kicker={t.tournament.kicker} title={t.tournament.title} lead={t.tournament.lead} />
      <div id="matchup" className="scroll-mt-24">
        <MatchupView locale={locale} />
      </div>
      <div className="mt-10">
        <TournamentJourney locale={locale} />
      </div>
    </Page>
  );
}
