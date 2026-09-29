import Image from "next/image";
import Link from "next/link";
import type { ReactNode } from "react";
import { teamAssets } from "@/lib/assets";
import { presentation } from "@/data/teamPresentation";

export function Page({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`mx-auto w-full max-w-standard px-5 pb-20 pt-10 md:px-8 md:pt-14 ${className}`}>{children}</div>;
}

export function PageHeader({ kicker, title, lead, right }: { kicker: string; title: ReactNode; lead?: ReactNode; right?: ReactNode }) {
  return (
    <header className="flex flex-col gap-5 md:flex-row md:items-end md:justify-between">
      <div className="max-w-3xl">
        <p className="kicker">{kicker}</p>
        <h1 className="mt-3 text-h1 font-semibold text-fg">{title}</h1>
        {lead && <p className="mt-3 text-body text-mute">{lead}</p>}
      </div>
      {right}
    </header>
  );
}

export function Panel({ children, className = "", as: Tag = "section" }: { children: ReactNode; className?: string; as?: "section" | "div" | "article" }) {
  return <Tag className={`panel min-w-0 p-5 md:p-7 ${className}`}>{children}</Tag>;
}

export function PanelTitle({ title, sub, right }: { title: ReactNode; sub?: ReactNode; right?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <h2 className="text-h3 font-semibold text-fg">{title}</h2>
        {sub && <p className="mt-1 text-caption text-mute">{sub}</p>}
      </div>
      {right}
    </div>
  );
}

export function LinkButton({ href, children, variant = "primary" }: { href: string; children: ReactNode; variant?: "primary" | "ghost" }) {
  const cls = variant === "primary"
    ? "bg-gradient-to-b from-gold-soft to-gold-deep text-navy hover:brightness-110"
    : "border border-line-strong text-gold-soft hover:border-gold";
  return <Link href={href} className={`inline-flex items-center rounded-full px-5 py-2 text-body font-semibold transition ${cls}`}>{children}</Link>;
}

/** Official club logo; renders nothing when no verified logo exists. */
export function TeamLogo({ id, size, className = "", priority = false }: { id: string; size: number; className?: string; priority?: boolean }) {
  const src = teamAssets(id)?.teamLogo;
  if (!src) return null;
  return (
    <Image src={src} alt={presentation(id).displayNameZh} width={size} height={size} priority={priority}
      className={`shrink-0 object-contain ${className}`} style={{ width: size, height: size }} />
  );
}

export function Signature({ size = "md" }: { size?: "sm" | "md" }) {
  return <span className={`font-[family-name:var(--font-script)] leading-none text-gold-soft ${size === "sm" ? "text-[18px]" : "text-[26px]"}`}>LLyra</span>;
}
