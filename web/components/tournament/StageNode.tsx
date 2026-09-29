"use client";

import { motion } from "framer-motion";

export const NODE_W = 6;

/** A stage node in the simulated probability flow (SVG). Height encodes probability. */
export function StageNode({
  id, x, top, height, label, value, color, active, terminal = false, labelSide = "top", onHover, onSelect,
}: {
  id: string;
  x: number;
  top: number;
  height: number;
  label: string;
  value: string;
  color: string;
  active: boolean;
  terminal?: boolean;
  labelSide?: "top" | "right";
  onHover?: (id: string | null) => void;
  onSelect?: (id: string) => void;
}) {
  const h = Math.max(height, 1.5);
  const lx = labelSide === "right" ? x + NODE_W + 10 : x - 2;
  const ly = labelSide === "right" ? top + h / 2 - 4 : top - 34;
  return (
    <g
      onMouseEnter={() => onHover?.(id)}
      onMouseLeave={() => onHover?.(null)}
      onFocus={() => onHover?.(id)}
      onBlur={() => onHover?.(null)}
      onClick={() => onSelect?.(id)}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onSelect?.(id);
        }
      }}
      tabIndex={0}
      role="button"
      aria-label={`${label} ${value}`}
      className="cursor-pointer outline-none"
    >
      <rect x={x - 14} y={top - 56} width={NODE_W + 150} height={h + 68} fill="transparent" />
      <motion.rect
        x={x}
        width={NODE_W}
        initial={false}
        animate={{ y: top, height: h }}
        transition={{ duration: 0.6, ease: [0.3, 0.6, 0.2, 1] }}
        fill={color}
        opacity={active ? 1 : terminal ? 0.7 : 0.9}
      />
      <motion.g initial={false} animate={{ x: lx, y: ly }} transition={{ duration: 0.6, ease: [0.3, 0.6, 0.2, 1] }}>
        <text fontSize="20" fill={active ? "#eef1f7" : "#97a3bb"}>{label}</text>
        <text y="26" fontSize="26" fill={terminal ? "#ff5064" : "#eef1f7"} fontFamily="var(--font-display)" fontWeight={600}>
          {value}
        </text>
      </motion.g>
    </g>
  );
}
