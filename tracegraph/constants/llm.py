PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_GEMINI = "gemini"

ANTHROPIC_DEFAULT_MODEL = "claude-opus-5-5"
ANTHROPIC_EFFORT = "high"
ANTHROPIC_FALLBACK_BETA = "server-side-fallback-2026-07-01"

# PRD D13: deterministic sampling where the provider accepts it (Claude Opus 5.5 rejects sampling parameters).
GEMINI_TEMPERATURE = 0.0
GEMINI_RETRY_ATTEMPTS = 4
GEMINI_RETRY_STATUS_CODES = (408, 429, 500, 502, 503, 504)
GEMINI_REFUSAL_REASONS = frozenset({"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "RECITATION", "IMAGE_SAFETY"})
GEMINI_NATIVE_BLOCK = "gemini_content"

STOP_END_TURN = "end_turn"
STOP_TOOL_USE = "tool_use"
STOP_MAX_TOKENS = "max_tokens"
STOP_REFUSAL = "refusal"
