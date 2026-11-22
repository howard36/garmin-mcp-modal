# garmin-mcp-modal

This repo runs [garmin_mcp](https://github.com/Taxuspt/garmin_mcp), an MCP server for Garmin Connect, on [Modal](https://modal.com). Your MCP clients (claude.ai, Claude Code, or any other client that connects to a URL) can then read your Garmin data without a server on your own computer.

By default the server offers only tools that read data. Modal rejects every request that does not carry your proxy token, which is a key and secret that you create in Modal. The server runs only while it handles requests, and it stops after 1 minute without one.

## What you need

- [uv](https://docs.astral.sh/uv/).
- A Modal account. The free Starter plan is enough.
- The Modal CLI, logged in: run `uv tool install modal`, then `modal setup`.
- A Garmin Connect account.

The commands below are for macOS and Linux shells. On Windows, run them in WSL.

## Set up

1. Clone this repo and open a terminal in it.
2. Log in to Garmin to create a token for the server. The command asks for your email, password and MFA code:
   ```
   uv run garmin-mcp-auth --token-path ~/.garminconnect-modal --force-reauth
   ```
   The token goes into its own folder, so that the server does not share a login with a copy of garmin_mcp that runs on your computer. `--force-reauth` makes it log in again even when an older token is already there.
3. Deploy the server:
   ```
   modal deploy modal_app.py
   ```
   The output shows the server URL, for example `https://<workspace>--garmin-mcp-serve.us-east.modal.run`.
4. Upload the Garmin token:
   ```
   modal volume put garmin-tokens ~/.garminconnect-modal/garmin_tokens.json /garmin_tokens.json
   ```
5. Create a proxy token. Modal shows the secret only once, so save the key and the secret in your password manager:
   ```
   modal workspace proxy-tokens create
   ```
6. Test the server with your proxy token's ID and secret:
   ```
   MODAL_KEY=wk-... MODAL_SECRET=ws-... uv run scripts/smoke_test.py
   ```
   Each result line starts with `[PASS]` when the server works. If a line fails, or a client can't connect later, the server logs show why: `modal app logs garmin-mcp`.

## Connect a client

Give your client the server URL with `/mcp` at the end, and this request header, with your proxy token's ID and secret joined by a dot:

```
Authorization: Bearer <token-id>.<token-secret>
```

For example, `Bearer wk-abc123.ws-def456`.

Modal also accepts the token as two headers, `Modal-Key` and `Modal-Secret`. Use these if your client already uses the `Authorization` header for something else.

In claude.ai, add the server as a custom connector. Under **Authentication**, choose **No sign-in**, and put the `Authorization` header under **Request headers**. The connector then works in claude.ai on the web, desktop and mobile, and in Claude Code.

Other clients work if they support the Streamable HTTP transport and let you set request headers.

## Choose the tools

To change which tools the server offers, set these variables in the same command as `modal deploy`. The deploy reads them from your shell, including any that you set earlier for a local garmin_mcp. A deploy without them goes back to the default of all read-only tools.

| Variable | Effect |
|---|---|
| `GARMIN_TOOL_PROFILE` | Offers only the tools for one area: `health`, `activities`, `training`, `workouts`, `nutrition` or `minimal`. To combine areas, separate them with commas. |
| `GARMIN_ENABLED_TOOLS` | A comma-separated list of tool names. Without a profile, the server offers only these tools. With a profile, they are added to it. Write tools are left out unless `GARMIN_MCP_ALLOW_WRITES` is `true`. |
| `GARMIN_DISABLED_TOOLS` | A comma-separated list of tool names to remove. |
| `GARMIN_MCP_ALLOW_WRITES` | `true` also offers the tools that create, change or delete data in Garmin Connect. |

For example:

```
GARMIN_TOOL_PROFILE=health modal deploy modal_app.py
```

Before you set `GARMIN_MCP_ALLOW_WRITES=true`, set your client to ask for approval before it uses a write tool. With write tools on, anyone who has your proxy token can change or delete your Garmin data.

## When Garmin tools return authentication errors

The server renews its Garmin access token every day without your help. The login behind it lasts for months, but it can end, for example when you change your Garmin password. To log in again:

1. Stop the server, so that it does not write its old token over the new one:
   ```
   modal app stop garmin-mcp
   ```
2. Log in again, as in step 2 of the setup.
3. Upload the new token. `--force` replaces the old file:
   ```
   modal volume put --force garmin-tokens ~/.garminconnect-modal/garmin_tokens.json /garmin_tokens.json
   ```
4. Deploy again, with the same tool variables as before.

## Update garmin_mcp

1. In `pyproject.toml`, change `rev` to the new commit of garmin_mcp.
2. Run `uv lock`.
3. Deploy again and run the smoke test.

## License

MIT. See [LICENSE](LICENSE). garmin_mcp is also MIT-licensed.
