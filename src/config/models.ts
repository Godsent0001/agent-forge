export const DEFAULT_MODELS = {
  anthropic: "claude-haiku-4-5-20251001",
  openai: "gpt-4o-mini",
  google: "gemini-2.5-flash",
} as const;

export type Provider = keyof typeof DEFAULT_MODELS;
