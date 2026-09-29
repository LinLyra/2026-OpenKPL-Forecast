import type { Metadata } from "next";
import { MatchupView } from "@/components/matchup/MatchupView";
import { dict } from "@/lib/i18n";

export const metadata: Metadata = { title: dict("zh").matchup.title };

export default function Page() {
  return <MatchupView locale="zh" />;
}
