"""Maps AgentForge provider ids to LiteLLM provider prefixes and builds the "<prefix>/<model>" string."""

# The UI stores Google AI Studio agents as "gemini" (or "google" for older agents). LiteLLM has no "google/" route.
LITELLM_PROVIDER_PREFIX: dict[str, str] = {"google": "gemini"}


def litellm_model(provider: str | None, model: str) -> str:
    if not provider:
        return model
    return f"{LITELLM_PROVIDER_PREFIX.get(provider, provider)}/{model}"
