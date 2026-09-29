import type { Metadata } from "next";
import { TeamsView } from "@/components/teams/TeamsView";
import { dict } from "@/lib/i18n";

export const metadata: Metadata = { title: dict("zh").teams.title };

export default function Page() {
  return <TeamsView locale="zh" />;
}
