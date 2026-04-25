# kimi-to-im

> Chat with the [Kimi CLI](https://github.com/MoonshotAI/kimi-cli) from Telegram. Self-hosted, single-user, ~600 lines of Python.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://github.com/Alfa-ai-ccvs-tech/kimi-to-im/actions/workflows/test.yml/badge.svg)](https://github.com/Alfa-ai-ccvs-tech/kimi-to-im/actions/workflows/test.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

You already use Kimi CLI at your desk. This bridge lets you keep the same conversation going from your phone — over Telegram — without changing how Kimi runs locally. You send a message, the bridge spawns `kimi` on your machine, and the reply lands back in Telegram. Sessions persist per chat, so follow-ups pick up where you left off.

```text
   📱  Telegram             🖥  your machine
  ┌─────────┐    HTTPS    ┌──────────────┐    spawn       ┌──────────┐
  │  phone  │  ◀───────▶  │  bridge.py   │  ───────────▶  │   kimi   │
  └─────────┘             │  (systemd)   │   subprocess   │   CLI    │
                          └──────────────┘                └──────────┘
                            chat → session map persisted in
                            ~/.kimi/bridge/state.json
```

## Why this exists

If you live in Kimi but spend half your day away from your laptop, you lose context every time you switch to your phone. This bridge keeps your Kimi sessions reachable anywhere Telegram is — for the cost of one bot token and a systemd user service.

It is **single-user, single-host, text-only** by design. There is no cloud component, no account system, and no shared state. The bot replies only to user IDs you explicitly whitelist in `config.json`.

## Quickstart

You need: Linux with `systemd --user`, Python 3.11+, [`uv`](https://docs.astral.sh/uv/), and a working `kimi` CLI on your `PATH`. Full prerequisites and verification commands live in [`docs/deployment.md`](docs/deployment.md).

**1. Get a Telegram bot token.** Message [@BotFather](https://t.me/BotFather), send `/newbot`, follow the prompts. Copy the token.

**2. Get your Telegram user ID.** Message [@userinfobot](https://t.me/userinfobot). It replies with your numeric ID.

**3. Install.**

```sh
git clone https://github.com/Alfa-ai-ccvs-tech/kimi-to-im.git ~/.kimi/plugins/telegram-bridge
cd ~/.kimi/plugins/telegram-bridge
bash install.sh
```

> Expected: a `.venv/` is created and a systemd user unit registered.

**4. Configure.**

```sh
cp config.example.json config.json
chmod 600 config.json
$EDITOR config.json   # paste bot_token, add your Telegram user ID to allowed_user_ids
```

**5. Start.**

```sh
systemctl --user start kimi-telegram-bridge.service
```

> Expected: `systemctl --user is-active kimi-telegram-bridge.service` prints `active`. Send "hello" to your bot from Telegram — within ~10s the typing indicator appears, then a Kimi reply.

For a more detailed walk-through with pre-flight checks and smoke tests, see [`docs/deployment.md`](docs/deployment.md).

## How it works

A small Python daemon long-polls Telegram's `getUpdates` API. When it sees a message from an allowed user it spawns `kimi --print --output-format stream-json -S <session_id>`, captures the reply, and posts it back to the same chat. A `chat_id → session_id` map is persisted at `~/.kimi/bridge/state.json` so each Telegram chat continues the same Kimi session across daemon restarts.

The daemon is supervised by `systemctl --user`. A small Kimi plugin (`bridge` tool) is also registered so you can manage the daemon from inside Kimi itself:

```sh
kimi -p "use the bridge tool with action=status"
```

For the full architecture write-up, see [`docs/design.md`](docs/design.md).

## Configuration

The full reference lives in [`docs/operations.md`](docs/operations.md#configure-the-bridge). The minimum to know:

| Field | Required | Purpose |
|---|---|---|
| `telegram.bot_token` | yes | The string from BotFather. |
| `telegram.allowed_user_ids` | yes | Whitelist of Telegram user IDs. Empty = nobody can talk to the bot (default-deny). |
| `telegram.allowed_chat_ids` | recommended | Optional chat-level whitelist. Set to your DM's chat id (= your user id) so the bot won't respond inside groups. |
| `kimi.default_workdir` | no | Where Kimi runs. Defaults to Kimi's own default. |
| `kimi.model` | no | Empty = Kimi's default model. |

`config.json` is gitignored. Don't commit your token.

## Limitations

This is intentionally a small, opinionated tool. It does **not**:

- support Discord, Slack, Feishu, QQ, or any IM other than Telegram;
- handle images, voice, or file uploads — text only;
- stream replies token-by-token (Kimi emits per-turn JSON, the bridge sends per-turn);
- expose Kimi's internal tool calls or ask for permission before they run;
- sync state between machines — one bridge per host.

If you need any of these, this bridge is the wrong tool.

## Documentation

| Document | Read this when... |
|---|---|
| [`docs/deployment.md`](docs/deployment.md) | You're installing for the first time. |
| [`docs/operations.md`](docs/operations.md) | You're running the bridge day-to-day, or troubleshooting. |
| [`docs/design.md`](docs/design.md) | You want to understand why the architecture looks the way it does. |
| [`docs/security-scan.md`](docs/security-scan.md) | You want the formal pre-publication audit findings. |
| [`SECURITY.md`](SECURITY.md) | You found a vulnerability or want the security policy. |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | You want to send a patch. |

## Contributing

PRs welcome. Please read [`CONTRIBUTING.md`](CONTRIBUTING.md) and run the tests:

```sh
uv venv .venv --python 3.11
uv pip install -e ".[dev]"
.venv/bin/pytest -v
```

The full suite runs in under 2 seconds and is the gate for CI.

## License

MIT — see [LICENSE](LICENSE).
