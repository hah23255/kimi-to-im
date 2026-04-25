# kimi-to-im

Telegram bridge for the [Kimi CLI](https://github.com/MoonshotAI/kimi-cli) — chat with Kimi from Telegram.

Architecture: a Python daemon polls Telegram, spawns `kimi --print --output-format stream-json -S <session>` per inbound message, and replies. The daemon is supervised by `systemctl --user`. A Kimi plugin manifest exposes the daemon's lifecycle (start/stop/status/logs/setup) as a callable tool inside Kimi sessions.

See [`docs/design.md`](docs/design.md) for the architecture spec.

## Install

```sh
cd ~/.kimi/plugins/telegram-bridge
bash install.sh
cp config.example.json config.json
$EDITOR config.json   # set telegram.bot_token and telegram.allowed_user_ids
systemctl --user start kimi-telegram-bridge.service
```

## Usage from inside Kimi

```sh
kimi -p "use the bridge tool with action=status"
kimi -p "use the bridge tool with action=logs and lines=100"
kimi -p "use the bridge tool with action=setup"
```

## Configuration

Edit `config.json`. The minimum:

| Field | Required? | Notes |
|---|---|---|
| `telegram.bot_token` | yes | from `@BotFather` |
| `telegram.allowed_user_ids` | yes | non-empty (default-deny) |
| `telegram.allowed_chat_ids` | optional | empty = allow any chat from an allowed user |
| `kimi.default_workdir` | optional | working dir kimi runs in |
| `kimi.model` | optional | empty = kimi's default |
| `kimi.agent` | optional | defaults to `default` |

`config.json` is gitignored — never commit your bot token.

## Operating

- **Start**: `systemctl --user start kimi-telegram-bridge.service`
- **Stop**: `systemctl --user stop kimi-telegram-bridge.service`
- **Status**: `systemctl --user status kimi-telegram-bridge.service`
- **Logs**: `tail -f ~/.kimi/bridge/logs/bridge.log` (or `journalctl --user -u kimi-telegram-bridge.service -f`)

The daemon keeps a `chat_id → kimi session_id` map at `~/.kimi/bridge/state.json` so each Telegram chat resumes the same Kimi session across messages.

## Development

```sh
uv venv .venv --python 3.11
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -v
```
