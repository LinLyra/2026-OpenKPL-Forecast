import Image from "next/image";
import type { PlayerAssets } from "@/lib/assets";
import { dict, type Locale } from "@/lib/i18n";

export function PlayerCard({ player, locale, size = "md" }: { player: PlayerAssets; locale: Locale; size?: "sm" | "md" }) {
  const t = dict(locale);
  const px = size === "sm" ? 64 : 112;
  return (
    <figure className="flex flex-col items-center text-center">
      <span className="rounded-full bg-gradient-to-b from-gold-soft to-gold-deep p-[2px]">
        {player.playerPortrait ? (
          <Image src={player.playerPortrait} alt={player.name} width={px} height={px}
            className="rounded-full bg-ink-850 object-cover" style={{ width: px, height: px }} />
        ) : (
          <span className="block rounded-full bg-ink-850" style={{ width: px, height: px }} />
        )}
      </span>
      <figcaption className="mt-3">
        <p className={`${size === "sm" ? "text-body" : "text-h3"} font-semibold text-fg`}>{player.name}</p>
        {size === "md" && player.realName && locale === "zh" && <p className="text-caption text-mute">{player.realName}</p>}
        {player.position && <p className="mt-1 text-micro font-medium text-gold">{t.positions[player.position]}</p>}
      </figcaption>
    </figure>
  );
}
