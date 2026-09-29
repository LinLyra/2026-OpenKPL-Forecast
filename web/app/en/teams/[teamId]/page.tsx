import { TeamOverview } from "@/components/teams/views/TeamOverview";

export default async function Page({ params }: { params: Promise<{ teamId: string }> }) {
  const { teamId } = await params;
  return <TeamOverview locale="en" teamId={teamId} />;
}
