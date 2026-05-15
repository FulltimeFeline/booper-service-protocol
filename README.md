# booper-service-protocol

The integration contract for the
Booper iOS app, plus
two working reference implementations you can drop on any Linux box.

If you've ever wanted to monitor and control a long-running service
(a trading bot, an LLM agent, a scraper, a cron-driven pipeline, a
homegrown daemon — anything that runs in a loop and has state worth
seeing) from your phone over SSH, this is the contract Booper speaks.

There is **no SDK to depend on**, no auth tokens to ship, no central
backend to enroll in. Your service exposes a tiny CLI; Booper SSHes in
and runs subcommands; the CLI prints JSON to stdout. That's it.

## What "speaking the protocol" gets you

When Booper recognizes your service, the app gives it a dedicated
dashboard with:

- **Live metric tiles** — equity, error rate, tasks today, whatever your
  service publishes. Trends with deltas. Sparklines from your time
  series. The metric vocabulary is per-service-kind so a trading service
  shows positions, a monitoring service shows error rate + uptime, an
  agent shows tokens + success rate, etc.
- **Activity feed** — every event your service emits, with kind-aware
  icons and color coding (`tradeWin` is green, `error` is red, etc.).
- **Tappable commands** — the service declares its own command set
  (`pause`, `flatten`, `restart-pipeline`, anything). Booper renders a
  grid of buttons; taps SSH in and run them. Dangerous commands get a
  confirmation prompt.
- **Per-category push notifications** — declare which event types your
  service can push for, and the app surfaces per-category on/off toggles
  in the service detail view. Mute "warning" pushes from one service
  without muting the others.

All of that comes from ~60 lines of CLI on your side if you want the
basics, ~300 if you want every feature.

## Two reference implementations

| | `snapshot.sh` | `reference_service.py` |
|---|---|---|
| Lines | ~150 bash | ~370 Python |
| Deps | none | stdlib only |
| What it surfaces | host metrics (load/mem/disk/uptime) + a few `systemctl` commands | full demo: trading metrics, positions, trades, declared commands, push notifications |
| Best for | giving any random Linux box a Booper dashboard with zero per-service code | the template you fork to implement a real service |

Both live in `examples/`.

## Quick start

### Tier 1 — drop-in shell, no code changes

```bash
curl -fsSL https://raw.githubusercontent.com/fulltimefeline/booper-service-protocol/main/examples/snapshot.sh \
    -o /usr/local/bin/service && chmod +x /usr/local/bin/service
```

In Booper: **Add Service** on the server you installed it on, set the
command to `service`, kind to **Generic**. Save. You'll see live host
metrics within 30 seconds.

### Tier 2 — fork the reference and replace the demo data

```bash
curl -fsSL https://raw.githubusercontent.com/fulltimefeline/booper-service-protocol/main/examples/reference_service.py \
    -o /usr/local/bin/service && chmod +x /usr/local/bin/service
```

Open it up, replace the demo `cmd_snapshot` body with a read from your
service's actual state (DB, IPC, state file, Prometheus, whatever), and
you have a fully populated dashboard. The rest of the subcommands
(`activity`, `commands`, `run`, push hooks) follow the same shape.

## The full spec

See [`PROTOCOL.md`](PROTOCOL.md). Every field Booper reads is documented
there with the JSON shape, the types, and which UI element it drives.
The doc is the source of truth for the protocol; the iOS app and these
references should match it byte-for-byte.

## Push notifications

Push is **separate from the protocol** — your service doesn't need APNs
auth keys or Apple Developer credentials. Each server can run the
optional [booper-watchdog](https://github.com/fulltimefeline/booper-watchdog),
which installs a `booper-notify` shim. Your service then shells out to
it:

```bash
booper-notify alert \
    --title "Trade closed" \
    --body  "+$23.40 on FOMC" \
    --category trade.win \
    --bot-id  dawnbot
```

The shim talks to the
[booper-relay](https://github.com/fulltimefeline/booper-relay) which
signs the APNs JWT and forwards the push. End-to-end: about 1 second
from your service to the lock screen.

Including `--category` + `--bot-id` lets the iOS app render per-service
mute toggles for each event type the service emits. The first push of a
new category auto-creates the toggle.

## Authentication

SSH keys. There's no "service API key". Booper authenticates as the
server's SSH user; the service CLI inherits that identity. No extra
secrets to provision, rotate, or leak.

## Service kinds (UI hints)

When you add a service, you pick one of:

| Kind          | What it gives you                                                |
|---------------|------------------------------------------------------------------|
| `generic`     | Standard metric / activity / commands shell                       |
| `trading`     | + Positions section, Win Rate donut, Top Markets bar              |
| `monitoring`  | + Activity breakdown tuned for alerts                             |
| `agent`       | + Activity breakdown tuned for task success / failure             |
| `automation`  | + Activity breakdown tuned for pipeline runs                      |
| `scraper`     | + Activity breakdown tuned for batches & rate-limits              |

These are pure UI affordances — they don't change the protocol. A
trading service and a generic service speak the same CLI; trading just
adds three extra subcommands (`positions`, `trades`, `markets`).

## Versioning

The protocol is semver. Breaking changes (renamed fields, changed types)
bump the major. New optional fields bump the minor. Booper iOS commits
to backwards-compatibility within a major.

Current version: **v2.0** — what's documented in `PROTOCOL.md`.

## Contributing

Found a field Booper reads that isn't documented? PRs welcome. The
spec doc is the contract; if the iOS app does something the doc doesn't
say, that's a bug in the doc.

## License

MIT. See `LICENSE`.
