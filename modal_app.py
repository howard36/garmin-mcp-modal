"""Garmin Connect MCP server (Taxuspt/garmin_mcp) on Modal.

Deploy with `modal deploy modal_app.py`. The server answers at the URL that the
deploy prints, with /mcp at the end. Modal proxy auth protects it (see README).
"""

import os
import subprocess
from pathlib import Path

import modal

PORT = 8000
TOKENS_DIR = "/tokens"
TOKEN_FILE = Path(TOKENS_DIR) / "garmin_tokens.json"

# Tool settings, read from your shell when you run `modal deploy`.
# The first three are upstream's; the last one is this repo's.
CONFIG_KEYS = (
    "GARMIN_TOOL_PROFILE",
    "GARMIN_ENABLED_TOOLS",
    "GARMIN_DISABLED_TOOLS",
    "GARMIN_MCP_ALLOW_WRITES",
)
CONFIG = {key: os.environ[key] for key in CONFIG_KEYS if os.environ.get(key)}

# pyproject.toml pins garmin_mcp to one commit; uv.lock pins everything with hashes.
image = modal.Image.debian_slim(python_version="3.12").apt_install("git").uv_sync(
    str(Path(__file__).parent)
)

app = modal.App("garmin-mcp", image=image)
# The garminconnect library rewrites the token file when it refreshes the token.
# Modal commits volume changes in the background and on shutdown, so the new token persists.
tokens = modal.Volume.from_name("garmin-tokens", create_if_missing=True)


def _names(value: str | None) -> set[str]:
    return {name.strip().lower() for name in (value or "").split(",") if name.strip()}


def _tool_filter_env() -> dict[str, str]:
    """Upstream's tool settings, reduced to one allowlist of read-only tools unless writes are allowed."""
    if CONFIG.get("GARMIN_MCP_ALLOW_WRITES", "").lower() in ("1", "true", "yes", "on"):
        return {key: CONFIG[key] for key in CONFIG_KEYS[:3] if key in CONFIG}

    from garmin_mcp.tool_annotations import READ_ONLY_TOOLS
    from garmin_mcp.tool_profiles import resolve_tool_profile

    profile = resolve_tool_profile(CONFIG.get("GARMIN_TOOL_PROFILE"))  # None means every tool
    enabled = _names(CONFIG.get("GARMIN_ENABLED_TOOLS"))
    disabled = _names(CONFIG.get("GARMIN_DISABLED_TOOLS"))

    # Same meaning as upstream: a profile plus the allowlist, or the allowlist alone.
    selected = (set(profile) | enabled) if profile is not None else (enabled or set(READ_ONLY_TOOLS))
    allowed = (selected - disabled) & READ_ONLY_TOOLS
    if enabled - READ_ONLY_TOOLS:
        print(f"Not served (unknown or not read-only): {', '.join(sorted(enabled - READ_ONLY_TOOLS))}", flush=True)
    if not allowed:
        raise ValueError("No read-only tools left to serve. Check your GARMIN_* tool settings.")
    return {"GARMIN_ENABLED_TOOLS": ",".join(sorted(allowed))}


@app.function(
    volumes={TOKENS_DIR: tokens},
    env=CONFIG,
    # One container: only one process ever refreshes and writes the Garmin token.
    max_containers=1,
    # Stay warm for a minute so a conversation's tool calls hit a running container.
    scaledown_window=60,
)
@modal.concurrent(max_inputs=20)
@modal.web_server(port=PORT, startup_timeout=60, requires_proxy_auth=True)
def serve():
    if not TOKEN_FILE.exists():
        print(
            f"WARNING: {TOKEN_FILE} missing. Upload it with "
            "`modal volume put garmin-tokens <file> /garmin_tokens.json`.",
            flush=True,
        )
    server_env = {
        "GARMIN_MCP_TRANSPORT": "streamable-http",
        "GARMIN_MCP_HOST": "0.0.0.0",
        "GARMIN_MCP_PORT": str(PORT),
        "GARMIN_MCP_STATELESS_HTTP": "true",
        "GARMINTOKENS": TOKENS_DIR,
        **_tool_filter_env(),
    }
    # Pass upstream only the computed settings, not the raw ones that `env=CONFIG` put in os.environ.
    base_env = {key: value for key, value in os.environ.items() if key not in CONFIG_KEYS}
    subprocess.Popen(["garmin-mcp"], env={**base_env, **server_env}, stdin=subprocess.DEVNULL)
