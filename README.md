# kimi-to-im

Telegram bridge for the [Kimi CLI](https://github.com/MoonshotAI/kimi-cli) — chat with Kimi from Telegram.

Installed as a Kimi plugin (`~/.kimi/plugins/telegram-bridge/`); the long-running bridge daemon is supervised by `systemctl --user`.

Status: **in development**. See [`docs/design.md`](docs/design.md) for the architecture spec.

## Layout

- `src/` — Python source for the daemon and the plugin control tool
- `systemd/` — user-unit template installed by `install.sh`
- `plugin.json` — Kimi plugin manifest
- `config.example.json` — template; copy to `config.json` and fill in your bot token

## Install

```sh
cd ~/.kimi/plugins/telegram-bridge
bash install.sh
cp config.example.json config.json
$EDITOR config.json   # set telegram.bot_token and telegram.allowed_user_ids
systemctl --user start kimi-telegram-bridge.service
```
