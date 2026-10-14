import { PROVIDERS } from "./providers";
import type { ModelOption } from "./providers";

export type { ModelOption } from "./providers";

export type Provider = (typeof PROVIDERS)[number]["id"];

/** Default model per provider id (derived from the provider registry). */
export const DEFAULT_MODELS: Record<string, string> = Object.fromEntries(
  PROVIDERS.map((provider) => [provider.id, provider.defaultModel]),
);

/**
 * Curated models per provider. Any other model can be entered via "Custom model ID".
 * Keep in sync with python-runtime/app/core/llm/models.yaml, which drives pricing and context windows;
 * a model missing there still runs but its cost shows as unknown.
 */
export const MODEL_OPTIONS: Record<string, ModelOption[]> = Object.fromEntries(
  PROVIDERS.map((provider) => [provider.id, provider.models]),
);
