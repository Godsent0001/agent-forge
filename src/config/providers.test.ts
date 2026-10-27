import { describe, expect, it } from "vitest";
import { DEFAULT_MODELS } from "./models";
import { PROVIDERS, getProvider, isKnownModel, normalizeProviderId, providersNeedingKeys } from "./providers";

describe("provider registry", () => {
  it("has unique provider ids and key slots", () => {
    expect(new Set(PROVIDERS.map((p) => p.id)).size).toBe(PROVIDERS.length);
    const slots = PROVIDERS.filter((p) => p.needsKey).map((p) => p.keyId);
    expect(new Set(slots).size).toBe(slots.length);
  });

  it("every provider's default model is one of its listed models", () => {
    for (const provider of PROVIDERS) {
      expect(provider.models.map((m) => m.value)).toContain(provider.defaultModel);
      expect(DEFAULT_MODELS[provider.id]).toBe(provider.defaultModel);
    }
  });

  it("keeps the original anthropic default so existing behaviour is unchanged", () => {
    expect(DEFAULT_MODELS.anthropic).toBe("claude-haiku-4-5-20251001");
  });

  it("maps the legacy 'google' provider to gemini but keeps the saved-key slot 'google'", () => {
    expect(normalizeProviderId("google")).toBe("gemini");
    expect(getProvider("google")?.id).toBe("gemini");
    expect(getProvider("gemini")?.keyId).toBe("google");
  });

  it("falls back to the default provider and returns undefined for unknown ones", () => {
    expect(normalizeProviderId(undefined)).toBe("anthropic");
    expect(getProvider("some-new-provider")).toBeUndefined();
  });

  it("knows which models are curated", () => {
    expect(isKnownModel("anthropic", "claude-sonnet-5-5")).toBe(true);
    expect(isKnownModel("anthropic", "claude-whatever")).toBe(false);
    expect(isKnownModel("anthropic", "")).toBe(false);
  });

  it("registers Venice with the configured default model and API key slot", () => {
    expect(getProvider("venice")?.keyId).toBe("venice");
    expect(getProvider("venice")?.defaultModel).toBe("deepseek-v4-1-flash-uncensored");
    expect(isKnownModel("venice", "deepseek-v4-1-flash-uncensored")).toBe(true);
    expect(providersNeedingKeys().some((p) => p.id === "venice")).toBe(true);
  });

  it("does not ask for a key for local providers", () => {
    expect(providersNeedingKeys().some((p) => p.id === "ollama")).toBe(false);
  });
});
