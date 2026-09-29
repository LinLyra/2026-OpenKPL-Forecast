import type { Metadata } from "next";
import type { ReactNode } from "react";
import { notFound } from "next/navigation";
import { TeamShell } from "@/components/teams/TeamShell";
import { getTeam, teamIds } from "@/lib/data";

export const dynamicParams = false;

export function generateStaticParams() {
  return teamIds.map((teamId) => ({ teamId }));
}

export async function generateMetadata({ params }: { params: Promise<{ teamId: string }> }): Promise<Metadata> {
  const { teamId } = await params;
  return { title: getTeam(teamId)?.official_name ?? teamId };
}

export default async function Layout({ children, params }: { children: ReactNode; params: Promise<{ teamId: string }> }) {
  const { teamId } = await params;
  if (!getTeam(teamId)) notFound();
  return <TeamShell locale="zh" teamId={teamId}>{children}</TeamShell>;
}
