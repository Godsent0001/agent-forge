export const DEFAULT_MODELS = {
  anthropic: "claude-haiku-4-5-20251001",
  openai: "gpt-4o-mini",
  google: "gemini-2.5-flash",
} as const;

export type Provider = keyof typeof DEFAULT_MODELS;

export interface ModelOption {
  value: string;
  label: string;
}

/**
 * Models offered in the agent settings. NOTE: keep in sync with python-runtime/app/core/llm/models.yaml,
 * which drives pricing and context windows; an ID missing there runs but shows "unknown" cost.
 */
export const MODEL_OPTIONS: Record<Provider, ModelOption[]> = {
  google: [
    { value: "gemini-2.5-flash", label: "gemini-2.5-flash (Fast & Reasoning)" },
    { value: "gemini-2.5-pro", label: "gemini-2.5-pro (Deep Analytics)" },
  ],
  openai: [
    { value: "gpt-4o-mini", label: "gpt-4o-mini" },
    { value: "gpt-4o", label: "gpt-4o" },
  ],
  anthropic: [
    { value: "claude-haiku-4-5-20251001", label: "claude-haiku-4-5" },
    // Alias instead of a dated snapshot: the previous value (…-20251001) looked like Haiku's date reused for Sonnet. Verify with a live key.
    { value: "claude-sonnet-4-5", label: "claude-sonnet-4-5" },
  ],
};
