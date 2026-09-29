import { TeamJourney } from "@/components/teams/views/TeamJourney";

export default async function Page({ params }: { params: Promise<{ teamId: string }> }) {
  const { teamId } = await params;
  return <TeamJourney locale="en" teamId={teamId} />;
}
