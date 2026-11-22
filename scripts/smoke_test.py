# /// script
# requires-python = ">=3.12"
# dependencies = ["mcp==1.30.0", "httpx==0.28.1", "modal>=1.5,<2"]
# ///
"""Check that the deployed Garmin MCP server works.

Usage:  MODAL_KEY=<token-id> MODAL_SECRET=<token-secret> uv run scripts/smoke_test.py [URL]

Without URL, looks up the deployed `garmin-mcp` app with your Modal login.
"""

import asyncio
import os
import sys

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"[{'PASS' if ok else 'FAIL'}] {label}{f' ({detail})' if detail else ''}")
    return ok


async def main(base: str, headers: dict[str, str]) -> int:
    base = base.rstrip("/")
    results = []

    async with httpx.AsyncClient(timeout=120) as http:
        r = await http.post(f"{base}/mcp", json={})
        results.append(check("rejects requests without proxy auth", r.status_code == 401, f"HTTP {r.status_code}"))

        # A cold container answers "pending" while the Garmin login runs in the background.
        for _ in range(30):
            r = await http.get(f"{base}/readyz", headers=headers)
            if '"pending"' not in r.text:
                break
            await asyncio.sleep(3)
        results.append(check("Garmin login ready (/readyz)", r.status_code == 200, f"HTTP {r.status_code} {r.text[:80]}"))

    mcp_http = httpx.AsyncClient(headers=headers, timeout=120, follow_redirects=True)
    async with mcp_http, streamable_http_client(f"{base}/mcp", http_client=mcp_http) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools
            writes = sum(1 for t in tools if not (t.annotations and t.annotations.readOnlyHint))
            results.append(check("lists tools", len(tools) > 0, f"{len(tools)} tools, {writes} can write"))

            if any(t.name == "get_unit_system" for t in tools):
                result = await session.call_tool("get_unit_system", {})
                text = " ".join(getattr(c, "text", "") for c in result.content)[:80]
                results.append(check("calls a Garmin tool (get_unit_system)", not result.isError, text))
            else:
                print("[SKIP] calls a Garmin tool (get_unit_system is not offered)")

    return 0 if all(results) else 1


if __name__ == "__main__":
    try:
        # The same header that the README tells clients to send.
        headers = {"Authorization": f"Bearer {os.environ['MODAL_KEY']}.{os.environ['MODAL_SECRET']}"}
    except KeyError:
        sys.exit("Set MODAL_KEY and MODAL_SECRET to your Modal proxy token.")
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        import modal

        url = modal.Function.from_name("garmin-mcp", "serve").get_web_url()
    print(f"Testing {url}")
    sys.exit(asyncio.run(main(url, headers)))
