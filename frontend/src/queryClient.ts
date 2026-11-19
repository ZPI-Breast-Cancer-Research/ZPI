import { QueryClient } from "@tanstack/react-query";

import { canRetry } from "./api";

// a 4xx won't change on another try
export const retryQuery = (failures: number, error: unknown) => failures < 2 && canRetry(error);

export function createQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: retryQuery } } });
}
