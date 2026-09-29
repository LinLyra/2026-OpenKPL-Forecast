import { en } from "@/locales/en";
import { zh, type Dict } from "@/locales/zh";

export type Locale = "zh" | "en";
export const LOCALES: Locale[] = ["zh", "en"];

export function dict(locale: Locale): Dict {
  return locale === "en" ? en : zh;
}

export function href(locale: Locale, path = ""): string {
  return `/${locale}${path}`;
}

export function teamName(locale: Locale, zhName: string, enName: string): string {
  return locale === "en" ? enName : zhName;
}
