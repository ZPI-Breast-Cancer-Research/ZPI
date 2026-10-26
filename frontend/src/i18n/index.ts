import { pl, type MessageKey } from "./pl";

const messages: Record<MessageKey, string> = pl;

export function t(key: MessageKey): string {
  return messages[key];
}

export type { MessageKey };
