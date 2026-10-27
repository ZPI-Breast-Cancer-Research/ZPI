import { pl, type MessageKey } from "./pl";

const messages: Record<MessageKey, string> = pl;

// t("models.promote", { v: "8" }) fills {v} in the message
export function t(key: MessageKey, values?: Record<string, string | number>): string {
  const text = messages[key];
  return values ? text.replace(/\{(\w+)\}/g, (match, name) => String(values[name] ?? match)) : text;
}

export type { MessageKey };
