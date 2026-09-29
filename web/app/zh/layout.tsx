import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import "@fontsource-variable/inter";
import "@fontsource/noto-sans-sc/400.css";
import "@fontsource/noto-sans-sc/500.css";
import "@fontsource/noto-sans-sc/600.css";
import "@fontsource/noto-sans-sc/700.css";
import "@fontsource/caveat/400.css";
import "../globals.css";
import { SiteShell } from "@/components/common/SiteShell";

export const metadata: Metadata = {
  title: { default: "2026 KPL 年度总决赛夺冠预测 | OpenKPL", template: "%s | OpenKPL 年总预测" },
  description: "2026 KPL 年度总决赛 12 支战队夺冠概率与对阵胜率，基于一百万次赛事模拟。",
};

export const viewport: Viewport = { themeColor: "#060912", width: "device-width", initialScale: 1 };

export default function ZhLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>
        <SiteShell locale="zh">{children}</SiteShell>
      </body>
    </html>
  );
}
