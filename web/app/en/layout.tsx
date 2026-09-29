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
  title: { default: "2026 KPL Annual Finals Title Forecast | OpenKPL", template: "%s | OpenKPL Forecast" },
  description: "Title odds and matchup odds for the 12 teams of the 2026 KPL Annual Finals, based on one million tournament simulations.",
};

export const viewport: Viewport = { themeColor: "#060912", width: "device-width", initialScale: 1 };

export default function EnLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <SiteShell locale="en">{children}</SiteShell>
      </body>
    </html>
  );
}
