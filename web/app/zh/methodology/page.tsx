import type { Metadata } from "next";
import { MethodologyView } from "@/components/methodology/MethodologyView";
import { dict } from "@/lib/i18n";

export const metadata: Metadata = { title: dict("zh").method.title };

export default function Page() {
  return <MethodologyView locale="zh" />;
}
