import type { Metadata } from "next";
import { TournamentView } from "@/components/tournament/TournamentView";
import { dict } from "@/lib/i18n";

export const metadata: Metadata = { title: dict("en").tournament.title };

export default function Page() {
  return <TournamentView locale="en" />;
}
