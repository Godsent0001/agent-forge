/**
 * Single source of truth for LLM providers in the UI.
 *
 * The backend routes every call through LiteLLM using "<provider>/<model>" (python-runtime/app/core/runner.py),
 * so id MUST be a LiteLLM provider prefix. Any model a provider offers can be used through the
 * "Custom model ID" option, so this list never needs to be exhaustive.
 *
 * NOTE: model IDs below (other than Anthropic's) come from general knowledge and have not been
 * exercised against live APIs from this repo; verify before relying on them in a demo.
 */

export interface ModelOption {
  value: string;
  label: string;
}

export interface ProviderInfo {
  /** LiteLLM provider prefix, stored on the agent as `provider`. */
  id: string;
  label: string;
  /**
   * Slot used for the stored API key (OS keychain + POST /settings/keys).
   * Differs from `id` only for Gemini, where "google" keeps already-saved keys working.
   */
  keyId: string;
  /** false for local runtimes such as Ollama. */
  needsKey: boolean;
  keyPlaceholder: string;
  defaultModel: string;
  models: ModelOption[];
  /** Hint shown in the custom model field. */
  customPlaceholder: string;
}

export const PROVIDERS: ProviderInfo[] = [
  {
    id: "anthropic",
    label: "Anthropic Claude",
    keyId: "anthropic",
    needsKey: true,
    keyPlaceholder: "sk-ant-…",
    defaultModel: "claude-haiku-4-5-20251001",
    customPlaceholder: "e.g. claude-opus-5-5",
    models: [
      { value: "claude-opus-5-5", label: "Claude Opus 5.5 (most capable)" },
      { value: "claude-sonnet-5-5", label: "Claude Sonnet 5.5 (balanced)" },
      { value: "claude-haiku-5-5", label: "Claude Haiku 5.5 (fast)" },
      { value: "claude-sonnet-4-5", label: "Claude Sonnet 4.5" },
      { value: "claude-haiku-4-5-20251001", label: "Claude Haiku 4.5" },
    ],
  },
  {
    id: "openai",
    label: "OpenAI",
    keyId: "openai",
    needsKey: true,
    keyPlaceholder: "sk-…",
    defaultModel: "gpt-4o-mini",
    customPlaceholder: "e.g. gpt-5",
    models: [
      { value: "gpt-5", label: "gpt-5" },
      { value: "gpt-5-mini", label: "gpt-5-mini" },
      { value: "gpt-4.1", label: "gpt-4.1" },
      { value: "gpt-4o", label: "gpt-4o" },
      { value: "gpt-4o-mini", label: "gpt-4o-mini" },
    ],
  },
  {
    id: "gemini",
    label: "Google Gemini",
    keyId: "google",
    needsKey: true,
    keyPlaceholder: "AIzaSy…",
    defaultModel: "gemini-2.5-flash",
    customPlaceholder: "e.g. gemini-2.5-flash-lite",
    models: [
      { value: "gemini-2.5-pro", label: "gemini-2.5-pro (deep analysis)" },
      { value: "gemini-2.5-flash", label: "gemini-2.5-flash (fast)" },
      { value: "gemini-2.5-flash-lite", label: "gemini-2.5-flash-lite (cheapest)" },
    ],
  },
  {
    id: "deepseek",
    label: "DeepSeek",
    keyId: "deepseek",
    needsKey: true,
    keyPlaceholder: "sk-…",
    defaultModel: "deepseek-chat",
    customPlaceholder: "e.g. deepseek-reasoner",
    models: [
      { value: "deepseek-chat", label: "deepseek-chat" },
      { value: "deepseek-reasoner", label: "deepseek-reasoner (reasoning)" },
    ],
  },
  {
    id: "mistral",
    label: "Mistral",
    keyId: "mistral",
    needsKey: true,
    keyPlaceholder: "Mistral API key",
    defaultModel: "mistral-large-latest",
    customPlaceholder: "e.g. codestral-latest",
    models: [
      { value: "mistral-large-latest", label: "mistral-large-latest" },
      { value: "mistral-small-latest", label: "mistral-small-latest" },
      { value: "codestral-latest", label: "codestral-latest" },
    ],
  },
  {
    id: "groq",
    label: "Groq",
    keyId: "groq",
    needsKey: true,
    keyPlaceholder: "gsk_…",
    defaultModel: "llama-3.3-70b-versatile",
    customPlaceholder: "e.g. llama-3.1-8b-instant",
    models: [
      { value: "llama-3.3-70b-versatile", label: "llama-3.3-70b-versatile" },
      { value: "llama-3.1-8b-instant", label: "llama-3.1-8b-instant" },
    ],
  },
  {
    id: "xai",
    label: "xAI Grok",
    keyId: "xai",
    needsKey: true,
    keyPlaceholder: "xai-…",
    defaultModel: "grok-3",
    customPlaceholder: "e.g. grok-3-mini",
    models: [
      { value: "grok-3", label: "grok-3" },
      { value: "grok-3-mini", label: "grok-3-mini" },
    ],
  },
  {
    id: "openrouter",
    label: "OpenRouter (any model)",
    keyId: "openrouter",
    needsKey: true,
    keyPlaceholder: "sk-or-…",
    defaultModel: "openai/gpt-4o-mini",
    customPlaceholder: "e.g. anthropic/claude-sonnet-4.5",
    models: [{ value: "openai/gpt-4o-mini", label: "openai/gpt-4o-mini" }],
  },
  {
    id: "venice",
    label: "Venice AI",
    keyId: "venice",
    needsKey: true,
    keyPlaceholder: "Venice API key",
    defaultModel: "deepseek-v4-1-flash-uncensored",
    customPlaceholder: "e.g. deepseek-v4-1-flash-uncensored",
    models: [
      { value: "deepseek-v4-1-flash-uncensored", label: "DeepSeek V4.1 Flash Uncensored" },
    ],
  },
  {
    id: "ollama",
    label: "Ollama (local)",
    keyId: "ollama",
    needsKey: false,
    keyPlaceholder: "",
    defaultModel: "llama3.1",
    customPlaceholder: "e.g. qwen2.5:7b",
    models: [{ value: "llama3.1", label: "llama3.1" }],
  },
];

/** Older agents stored "google"; LiteLLM's prefix for Google AI Studio is "gemini". */
const PROVIDER_ALIASES: Record<string, string> = { google: "gemini" };

export const DEFAULT_PROVIDER_ID = "anthropic";

export function normalizeProviderId(id: string | null | undefined): string {
  const raw = (id || DEFAULT_PROVIDER_ID).toLowerCase();
  return PROVIDER_ALIASES[raw] ?? raw;
}

/** Returns the provider definition, or undefined for an id the UI doesn't know (custom/legacy). */
export function getProvider(id: string | null | undefined): ProviderInfo | undefined {
  const normalized = normalizeProviderId(id);
  return PROVIDERS.find((provider) => provider.id === normalized);
}

export function providersNeedingKeys(): ProviderInfo[] {
  return PROVIDERS.filter((provider) => provider.needsKey);
}

export function isKnownModel(providerId: string | null | undefined, model: string | null | undefined): boolean {
  if (!model) return false;
  return !!getProvider(providerId)?.models.some((option) => option.value === model);
}
