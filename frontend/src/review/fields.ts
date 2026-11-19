import { hasMessage, t, type MessageKey } from "../i18n";

// a field name from the backend (extraction accuracy, quality gates); an older backend sends a label instead
export const anyFieldLabel = (field: string) => (hasMessage(`field.${field}`) ? t(`field.${field}` as MessageKey) : field);
