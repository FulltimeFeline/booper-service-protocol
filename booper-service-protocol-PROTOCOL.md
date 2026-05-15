# Booper Service Protocol — v2.0

The wire contract between the Booper iOS app and any **service** running
on a Linux host. A service is anything that runs in a loop and has state
worth seeing — a trading bot, an LLM agent, a scraper, a cron-driven
pipeline, a long-lived daemon, a custom monitoring shim.

This document is the source of truth. The iOS app's behavior and the
reference implementations should match it byte-for-byte. If they don't,
file an issue.

---

## 0. Tier 0 — no protocol needed

Add a server in Booper with SSH credentials. With zero integration you
get:

- **Terminal** — chat-style + classic mode, ANSI colors, persistent
  history, user-defined macros.
- **Files** — SFTP browser with grid + list, drag-and-drop, breadcrumb
  navigation.
- **Live host stats** — load average, memory, disk, uptime, OS, kernel,
  CPU count, RAM. Parsed from `/proc/*`, `df`, `uname`,
  `/etc/os-release`. Works on every modern Linux distro.
- **Pre-baked commands** — `systemctl status <name>`,
  `journalctl -fu <name>`, `df -h`, `free -h`, `docker ps`.
- **Optional push alerts** — install the watchdog from the server
  detail page. Disk-fill, service-down, load-spike, and whole-server-
  down (heartbeat) pushes land on your phone. Pure bash + a small
  hosted relay you can self-host.

No CLI, no agent. Just `sshd`. The rest of this document is the optional
layer for **structured per-service dashboards** on top.

---

## 1. Tier 1 — drop-in shell

If you want a service-style dashboard for a host but don't want to
maintain code, drop the `examples/snapshot.sh` script onto the host:

```bash
curl -fsSL .../snapshot.sh -o /usr/local/bin/service && chmod +x $_
```

In Booper, add a service with command name `service`. You get a dashboard
of host metrics rendered as a service. Extend the script's
`cmd_snapshot` / `cmd_commands` / `cmd_run` functions to expose anything
specific to your workload. **~5 minutes**.

---

## 2. Tier 2 — file-based

Your existing service already writes state somewhere (a JSON file, a
SQLite DB, a Prometheus endpoint). Skip writing a CLI entirely: write
your state to a known path and let Booper `cat` it over SSH.

Convention:

```
~/.booper/<service-name>/snapshot.json
~/.booper/<service-name>/activity.jsonl
~/.booper/<service-name>/series/<metric>.csv
```

A 30-line shell wrapper picks the file based on the subcommand:

```bash
#!/usr/bin/env bash
case "${1:-}" in
    snapshot)  cat ~/.booper/$SERVICE/snapshot.json ;;
    activity)  tail -n "${2:-50}" ~/.booper/$SERVICE/activity.jsonl | jq -s . ;;
    *)         echo "[]" ;;
esac
```

No subprocess overhead, no IPC. Your service writes when it has news;
Booper reads when it polls. **~15 minutes**.

---

## 3. Tier 3 — full CLI

Maximum control. Write a CLI in your language of choice that:

- Reads your service's live state (database, in-memory, IPC).
- Prints JSON for each subcommand.
- Optionally shells out to `booper-notify` when events fire.

`examples/reference_service.py` is a complete Python implementation —
about 370 lines, stdlib only. Fork it, replace the demo data, ship.
**~1–2 hours for a basic implementation; half a day for a polished one
with push.**

---

## 4. The subcommands

The CLI Booper runs is whatever path you put in the **command** field
when adding the service in the app. Throughout this doc we call it
`service`. Each subcommand prints JSON to stdout; exit code 0 means
success.

| Subcommand | Frequency | Required? | Returns |
|---|---|---|---|
| `snapshot` | every poll (default 2 min) | yes | service state object |
| `activity --limit N` | every poll | recommended | array of activity events |
| `commands` | on detail view open | recommended | array of commands |
| `run NAME --param k=v` | when user taps a command | iff `commands` returns anything | result object |
| `series --metric KEY --range R` | when user opens a chart | optional | array of `{date, value}` |
| `notifications` | on detail view open | optional | array of declared notification categories |
| `register-device --token HEX` | once per fresh APNs token | optional | result object |
| `notify --title T --body B [--category K] [--bot-id ID]` | from your service code | optional | result object |
| `positions` | every poll | trading only | array of open positions |
| `trades --limit N` | once on detail view open | trading only | array of closed trades |
| `markets` | rarely | trading only | array of markets |

The iOS app gracefully handles non-zero exit codes and decoding errors —
a missing optional subcommand just means that section of UI doesn't
render. Only `snapshot` is truly required.

---

## 5. JSON shapes

### `snapshot`

```json
{
  "online": true,
  "lastSeen": "2026-05-15T12:34:56Z",
  "metrics": [
    {
      "key": "equity",
      "label": "Equity",
      "value": 12345.67,
      "kind": "currency",
      "unit": "USD",
      "trend": {
        "delta": 23.40,
        "deltaLabel": "today",
        "direction": "up",
        "inverse": false
      }
    }
  ],
  "primaryMetricKey": "equity"
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `online` | bool | yes | Renders the status dot. `false` shows the service as offline; `true` + connection success shows online. |
| `lastSeen` | ISO-8601 string | optional | Ignored by the iOS app — it stamps `lastSeen` to the receive time so freshness reflects actual data flow, not your clock. |
| `metrics` | `Metric[]` | yes | See below. |
| `primaryMetricKey` | string | optional | Which metric's value is the hero number on the service card. Defaults to the first metric. |

**Metric:**

| Field | Type | Notes |
|---|---|---|
| `key` | string | Stable identifier (`"equity"`, `"error_rate"`). Used by series + as the value's dedupe key. |
| `label` | string | Display label. |
| `value` | number | The numeric value. Decimal-friendly. |
| `kind` | string enum | `currency` / `number` / `percent` / `duration` / `text`. Drives formatting. |
| `unit` | string | Optional unit suffix for `number` kind (`"req/s"`). |
| `displayValue` | string | Optional override for `text` kind. |
| `trend` | object | Optional. See below. |

**Metric kinds:**

| Kind | Example value | Rendered as |
|---|---|---|
| `currency` | `12345.67` | `$12,345.67` |
| `number` | `742` | `742` (+ optional unit) |
| `percent` | `0.62` | `62.0%` |
| `duration` | `86400` | `1d 0h` (seconds in) |
| `text` | (uses `displayValue`) | the `displayValue` |

**Trend:**

| Field | Type | Notes |
|---|---|---|
| `delta` | number | Signed change vs prior period. |
| `deltaLabel` | string | `"today"`, `"1h"`, `"vs last week"` — free text. |
| `direction` | string enum | `up` / `down` / `flat`. |
| `inverse` | bool | `true` when "down is good" (error rate, latency, drawdown). Recolors the arrow. |

---

### `activity`

```json
[
  {
    "id": "uuid-or-stable-string",
    "timestamp": "2026-05-15T12:30:00Z",
    "kind": "tradeWin",
    "title": "Closed YES on Will the Fed cut rates?",
    "subtitle": "Size $250",
    "value": 23.40
  }
]
```

| Field | Type | Notes |
|---|---|---|
| `id` | string | Stable across polls — used for diffing the feed. |
| `timestamp` | ISO-8601 | When the event happened. Drives sort and relative labels. |
| `kind` | string enum | Drives icon + color. See below. |
| `title` | string | One-line headline. |
| `subtitle` | string | Optional. Second line in the row. |
| `value` | number | Optional. Shown as a signed currency on the right when present. |
| `systemImage` | string | Optional. SF Symbol override for the row icon. |

**Activity kinds:** `tradeWin` / `tradeLoss` / `success` / `warning` / `error` / `info` / `action`.

---

### `commands`

```json
[
  {
    "name": "pause",
    "label": "Pause trading",
    "detail": "Halt new entries. Existing positions remain open.",
    "systemImage": "pause.fill",
    "params": [
      {
        "name": "duration",
        "label": "Duration",
        "type": "string",
        "required": false,
        "placeholder": "30m"
      }
    ],
    "dangerous": false
  }
]
```

The iOS app renders a grid of these as tappable buttons. Tapping fires
`service run pause --param duration=30m`.

| Field | Type | Notes |
|---|---|---|
| `name` | string | What gets passed as the first arg to `service run`. |
| `label` | string | Button label. |
| `detail` | string | Subtitle / explanation. |
| `systemImage` | string | SF Symbol name. |
| `params` | `Param[]` | Optional. Surfaces an input sheet before the run. |
| `dangerous` | bool | `true` adds a red confirmation prompt before firing. |

**Param:**

| Field | Type | Notes |
|---|---|---|
| `name` | string | What gets passed as `--param name=value`. |
| `label` | string | Form field label. |
| `type` | string enum | `string` / `number` / `bool`. |
| `required` | bool | Validates the input sheet's submit button. |
| `placeholder` | string | UITextField placeholder. |

---

### `run NAME --param k=v`

```json
{ "ok": true, "message": "Trading paused." }
```

Or:

```json
{ "error": "Invalid amount." }
```

Booper shows `message` in a toast on success, surfaces `error` (or
stderr if no JSON) when `ok` is missing/false.

---

### `series --metric KEY --range R`

`R` is one of `day` / `week` / `month` / `all`. Output:

```json
[
  { "date": "2026-05-15T08:00:00Z", "value": 12300.50 },
  { "date": "2026-05-15T08:05:00Z", "value": 12345.67 }
]
```

The iOS app renders a line chart with scrubbing. Down-sample on your
side; the app doesn't.

---

### `notifications`

Optional. When your service implements this, the iOS app surfaces
per-category on/off toggles in the service detail. Without it, toggles
are auto-discovered from incoming pushes (less complete — categories
only appear once a push of that type has been received).

```json
[
  {
    "key": "trade.win",
    "label": "Trade wins",
    "detail": "Push when a position closes with positive P&L.",
    "systemImage": "checkmark.seal.fill",
    "defaultEnabled": true
  }
]
```

Aliases accepted on each field for forgiving parsing:
`id`/`name` for `key`, `title` for `label`, `description` for `detail`,
`symbol` for `systemImage`, `enabled`/`defaultsOn` for `defaultEnabled`.

---

### `register-device --token HEX`

Booper SSHes this when it first connects with an APNs device token in
hand. Optional — you only need it if your service wants to send pushes
directly (rather than through `booper-notify`, which handles tokens
itself).

```json
{ "ok": true, "message": "Token stored." }
```

---

### `notify --title T --body B [--category K] [--bot-id ID]`

Optional helper for sending a push from inside your service. The
reference implementation shells out to `booper-notify`, which the
watchdog installs. If your service wants its events to surface as
per-category toggles in the iOS app, include `--category` and
`--bot-id`:

```bash
service notify \
    --title "Trade closed" --body "+\$23.40" \
    --category trade.win --bot-id dawnbot
```

The `--bot-id` should equal the service's name in Booper (case-
insensitive). That's how the iOS app maps an incoming push back to the
service for muting / routing.

---

### Trading-only

If the service is **kind = trading**, also implement:

```bash
service positions
```

```json
[
  {
    "id": "uuid",
    "marketId": "fed-cut-june",
    "marketQuestion": "Will the Fed cut rates at the next FOMC?",
    "side": "yes",
    "size": 250.00,
    "entryPrice": 0.42,
    "currentPrice": 0.48,
    "openedAt": "2026-05-15T08:00:00Z"
  }
]
```

```bash
service trades --limit 100
```

```json
[
  {
    "id": "uuid",
    "marketId": "...",
    "marketQuestion": "...",
    "side": "yes",
    "size": 250.00,
    "entryPrice": 0.42,
    "exitPrice": 0.61,
    "closedAt": "2026-05-14T18:00:00Z",
    "resolved": true,
    "pnl": 47.50
  }
]
```

`resolved` defaults to `true` if omitted. Set `false` for pending /
unresolved trades so win-rate widgets exclude them.

`pnl` is optional. When omitted, the iOS app computes
`(exit - entry) * size` (side-aware — negated for NO trades). Set it
explicitly if your bot quotes prices in YES-implied terms for both
sides.

`side` accepts `yes` / `no` (any casing), `y` / `n`, `buy` / `sell`,
`long` / `short`, `true` / `false`, `1` / `0`. Unknown values fall back
to `yes`.

```bash
service markets
```

```json
[
  {
    "id": "fed-cut-june",
    "slug": "fed-cut-june",
    "question": "Will the Fed cut rates at the next FOMC?",
    "endDate": "2026-06-12T18:00:00Z"
  }
]
```

---

## 6. Polling cadence

The iOS app polls `snapshot` + `activity` (+ trading subcommands for
trading services) every **2 minutes** by default, while the relevant
view is on screen. Users can configure 10s / 30s / 1m / 2m / 5m in
Booper's settings.

The app dedupes near-simultaneous calls in-memory (a service won't get
polled more than once per 10 seconds even if multiple views ask). It
also persists the last successful snapshot to disk so cold launches
render instantly from cache while the next live fetch is in flight.

`commands`, `notifications`, `series`, `markets`, `trades` are fetched
on view open (not the poll cadence). `register-device` fires once per
new device token. `notify` fires when your service code calls it — the
app never polls `notify`.

---

## 7. Authentication

SSH keys. There is no separate "service API key." Every connection
inherits the server's SSH credentials.

Setup, once per server:

1. Generate or paste a private key when adding the server in Booper.
   Ed25519 recommended.
2. On the host: `echo "<public-key>" >> ~/.ssh/authorized_keys` for the
   user Booper connects as.
3. Done.

Your service CLI runs as that SSH user — give it whatever filesystem
permissions it needs.

---

## 8. Versioning

Semver. The current major is **v2**. Minor bumps add optional fields;
the iOS app commits to backwards-compat within a major.

When the protocol changes:

- Optional new fields → minor bump, no service-side changes needed.
- Renamed / removed / re-typed fields → major bump, services must
  upgrade.

The iOS app advertises the protocol version it speaks in its `User-Agent`
during SSH (informational only — there's no negotiation step).

---

## 9. Errors

Three failure modes the iOS app handles gracefully:

| Service emits | App reads as |
|---|---|
| Non-zero exit code | The subcommand failed. Renders an error toast / "unavailable" placeholder. |
| Valid JSON but missing required fields | Same as above. |
| Stderr text + zero exit | App ignores stderr unless the matching stdout is missing. |

Be liberal in what you accept (the app's DTOs tolerate alias keys and
mixed casing on enums); be strict in what you emit (single JSON document
per subcommand, no chatter on stdout).

---

## 10. Recommended path

- **Just want a host dashboard with no code changes** → Tier 1
  (`examples/snapshot.sh`).
- **One service per server, existing state files** → Tier 2 (file-based
  wrapper).
- **Custom service with rich metrics and commands** → Tier 3
  (`examples/reference_service.py` as the template).

You can mix tiers across servers — Booper doesn't care.
