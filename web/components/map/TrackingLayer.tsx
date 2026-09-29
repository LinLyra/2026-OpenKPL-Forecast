import type { Position } from "@/data/teamPresentation";
import { ROLE_COLOR } from "@/data/map/tactical";
import { toView, type TrackingPoint } from "@/lib/mapProjection";

const GLYPH: Record<"zh" | "en", Record<Position, string>> = {
  zh: { clash: "对", jungle: "野", mid: "中", farm: "发", roam: "游" },
  en: { clash: "C", jungle: "J", mid: "M", farm: "F", roam: "R" },
};

/**
 * Renders tracking points (reference-normalized) inside a map SVG. Works for illustration frames and for
 * observed minimap tracking: a point with a playerId and a portrait shows the portrait, a heroId shows a tag.
 */
export function TrackingLayer({ points, locale, focus, portraits = {}, side = "blue" }: {
  points: TrackingPoint[];
  locale: "zh" | "en";
  focus?: Position | null;
  portraits?: Record<string, string>;
  side?: "blue" | "red";
}) {
  const ring = side === "blue" ? "#4a9bff" : "#ff5064";
  return (
    <g>
      {points.map((p, i) => {
        const [x, y] = toView(p);
        const dim = focus && p.role !== focus;
        const color = p.role ? ROLE_COLOR[p.role] : ring;
        const portrait = p.playerId ? portraits[p.playerId] : undefined;
        const key = p.playerId ?? p.role ?? String(i);
        return (
          <g key={key} transform={`translate(${x.toFixed(2)} ${y.toFixed(2)})`} opacity={dim ? 0.28 : 1} style={{ transition: "opacity 300ms" }}>
            {!dim && focus && <circle r={30} fill={color} opacity={0.22} />}
            <circle r={17} fill="#070b14" stroke={ring} strokeWidth={3} />
            {portrait ? (
              <>
                <clipPath id={`clip-${key}`}><circle r={14} /></clipPath>
                <image href={portrait} x={-14} y={-14} width={28} height={28} clipPath={`url(#clip-${key})`} />
              </>
            ) : (
              <>
                <circle r={13} fill={color} />
                {p.role && (
                  <text textAnchor="middle" dy="0.36em" fontSize={14} fontWeight={700} fill="#070b14">{GLYPH[locale][p.role]}</text>
                )}
              </>
            )}
            {p.heroId && (
              <text y={32} textAnchor="middle" fontSize={11} fill="#eef1f7" stroke="#070b14" strokeWidth={3} paintOrder="stroke">{p.heroId}</text>
            )}
          </g>
        );
      })}
    </g>
  );
}
