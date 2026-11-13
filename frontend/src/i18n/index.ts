import { pl, type MessageKey } from "./pl";

const messages: Record<MessageKey, string> = pl;

// t("models.promote", { v: "8" }) fills {v} in the message
export function t(key: MessageKey, values?: Record<string, string | number>): string {
  const text = messages[key];
  return values ? text.replace(/\{(\w+)\}/g, (match, name) => String(values[name] ?? match)) : text;
}

export const hasMessage = (key: string): key is MessageKey => key in messages;

// Polish has three forms: 1 badanie, 2–4 badania (but 12–14 badań), 5+ badań
export function plural(n: number, one: MessageKey, few: MessageKey, many: MessageKey): string {
  const form = n === 1 ? one : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 12 || n % 100 > 14) ? few : many;
  return t(form, { n });
}

export type { MessageKey };
