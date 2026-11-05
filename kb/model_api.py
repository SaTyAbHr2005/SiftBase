"""Provider wire format and the free-tier fallback order. Every provider takes the same OpenAI-style request."""
import os
import re
from dataclasses import dataclass, field

# The judge alone uses Groq's default model, whose daily tokens answering would otherwise use up.
DEFAULT_CHAIN = "cloudflare,groq:openai/gpt-oss-20b,openrouter,mistral,mistral:ministral-8b-latest,gemini"
# Writing and claim checks need the strongest models; the small ones only as a last resort.
WRITER_CHAIN = "cloudflare,groq:qwen/qwen3.8-27b,openrouter,mistral,gemini,mistral:ministral-8b-latest,groq:openai/gpt-oss-20b"
THINK = re.compile(r"<think>.*?</think>", re.S)

# name -> (chat completions URL, key variable, default model, tokens one call may use in a minute)
CATALOG = {
    "cloudflare": ("https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/ai/v1/chat/completions",
                   "CLOUDFLARE_API_TOKEN", "@cf/qwen/qwen3-30b-a3b-fp8", None),
    "groq": ("https://api.groq.com/openai/v1/chat/completions", "GROQ_API_KEY", "openai/gpt-oss-120b", 7500),
    "openrouter": ("https://openrouter.ai/api/v1/chat/completions", "OPENROUTER_API_KEY", "openrouter/free", None),
    "mistral": ("https://api.mistral.ai/v1/chat/completions", "MISTRAL_API_KEY", "ministral-14b-latest", None),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "GEMINI_API_KEY",
               "gemini-3.5-flash", None),
}


@dataclass(frozen=True)
class Provider:
    name: str
    url: str
    model: str
    key: str = field(default="", repr=False)
    max_total: int | None = None
    max_output: int = 8192

    @property
    def label(self):
        return f"{self.name}:{self.model}"


# Providers that keep no inference data by default (Cloudflare Workers AI: zero retention, no training; Groq: no
# retention except opt-out abuse logs). OpenRouter's free models, Mistral and Gemini free tiers may log or train on it.
PRIVATE_SAFE = {"cloudflare", "groq"}


def private_mode(env=None) -> bool:
    """KB_PRIVATE is on unless set to "0", "false" or "no", so any other value keeps documents private."""
    return (os.environ if env is None else env).get("KB_PRIVATE", "1").strip().lower() not in ("0", "false", "no")


def build_providers(env, variable="KB_LLM_PROVIDERS", default=DEFAULT_CHAIN):
    """Chain entries are `name` or `name:model`. Entries without their key are left out of the chain.
    KB_PRIVATE keeps documents with PRIVATE_SAFE providers (see private_mode): the default chains just leave the
    others out, and a chain that names one on purpose is refused."""
    private = private_mode(env)
    explicit = bool(env.get(variable, "").strip()) or default not in (DEFAULT_CHAIN, WRITER_CHAIN)
    out = []
    for entry in env.get(variable, default).split(","):
        name, _, model = entry.strip().partition(":")
        if not name:
            continue
        if name not in CATALOG:
            raise ValueError(f"unknown provider {name!r} in KB_LLM_PROVIDERS: use {sorted(CATALOG)}")
        if private and name not in PRIVATE_SAFE:
            if explicit:
                raise ValueError(f"{variable} names {name!r}, which may log or train on documents; "
                                 f"set KB_PRIVATE=0 to allow it")
            continue
        url, key_name, default_model, max_total = CATALOG[name]
        needed = re.findall(r"{(\w+)}", url)
        if not env.get(key_name) or not all(env.get(n) for n in needed):
            continue
        out.append(Provider(name, url.format(**{n: env[n] for n in needed}), model or default_model, env[key_name],
                            max_total))
    return tuple(out)


def fit_output(provider, input_estimate, max_tokens):
    """The output limit to send, or None when this call cannot fit the provider's limits."""
    limit = min(max_tokens, provider.max_output)
    if provider.max_total is not None:
        limit = min(limit, provider.max_total - input_estimate)
    return limit if limit >= min(max_tokens, 256) else None


def request_spec(provider, system, user, max_tokens, json_mode=True):
    model = provider.model.lower()
    system += "\nReturn only a valid JSON object." if json_mode else ""
    if "qwen3" in model:
        system += "\n/no_think"
    payload = {"model": provider.model, "temperature": 0, "max_tokens": max_tokens,
               "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    if "gpt-oss" in model:
        payload["reasoning_effort"] = "low"
    return provider.url, {"Authorization": f"Bearer {provider.key}", "Content-Type": "application/json"}, payload


def response_parts(body):
    usage = body.get("usage") or {}
    choice = body["choices"][0]
    content = choice.get("message", {}).get("content")
    if isinstance(content, str):
        content = THINK.sub("", content).strip()
    return content, choice.get("finish_reason"), usage.get("prompt_tokens"), usage.get("completion_tokens")
