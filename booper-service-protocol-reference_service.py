#!/usr/bin/env python3
"""
Booper Reference Service — a minimal implementation of the Booper Service
Protocol v2 (SSH-based). Booper SSHes into your host and runs subcommands
of this script; each subcommand prints JSON to stdout.

Replace the in-memory demo state with real reads from your service
(database, state file, IPC to a long-running daemon, etc.). Every
subcommand below has a clear "REPLACE ME" boundary.

Install:
    sudo cp reference_service.py /usr/local/bin/service
    sudo chmod +x /usr/local/bin/service

Push notifications:
    Run the watchdog installer once per server (Booper → server detail →
    Install Watchdog). That drops `/usr/local/bin/booper-notify` which
    talks to the Booper push relay. This script then shells out to it —
    no APNs keys needed on your service host.

    To push:
        service notify --title "Trade closed" --body "+$23.40"
    which forwards to `booper-notify alert ...`.
"""

import argparse
import json
import os
import random
import subprocess
import sys
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path


# ---------------------------------------------------------------------------
# State (demo). Replace with your service's real data sources.
# ---------------------------------------------------------------------------

STATE_PATH = Path.home() / ".booper-reference-service.json"


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except Exception:
            pass
    return {
        "paused": False,
        "max_position": 500.0,
        "equity": 12_345.67,
        "started_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


SAMPLE_MARKETS = [
    {"id": "us-election-2028", "slug": "us-election-2028",
     "question": "Will the Democrats win the 2028 US presidential election?",
     "endDate": "2028-11-07T05:00:00Z"},
    {"id": "fed-cut-june", "slug": "fed-cut-june",
     "question": "Will the Fed cut rates at the next FOMC meeting?",
     "endDate": None},
    {"id": "btc-100k-eoy", "slug": "btc-100k-eoy",
     "question": "Will Bitcoin close above $100k on Dec 31?",
     "endDate": "2026-12-31T23:59:59Z"},
]


# ---------------------------------------------------------------------------
# Required subcommands
# ---------------------------------------------------------------------------

def cmd_snapshot(args) -> None:
    """Service state, polled every poll-cycle. REQUIRED.

    Print one JSON object: { online, metrics, primaryMetricKey }. See
    PROTOCOL.md §5 for the full field list and the metric `kind` vocabulary.
    """
    state = load_state()

    # ──────── REPLACE ME ──────────────────────────────────────────────
    # Real implementation: read from your service's database/state file/
    # in-process counters. Compute deltas vs the previous tick if you
    # want trends.
    equity = state["equity"] + random.uniform(-50, 50)
    today_pnl = round(equity - 12_300.00, 2)
    # ──────────────────────────────────────────────────────────────────

    print(json.dumps({
        "online": not state["paused"],
        "lastSeen": now_iso(),
        "metrics": [
            {
                "key": "equity",
                "label": "Equity",
                "value": round(equity, 2),
                "kind": "currency",
                "trend": {
                    "delta": today_pnl,
                    "deltaLabel": "today",
                    "direction": "up" if today_pnl > 0 else ("down" if today_pnl < 0 else "flat"),
                    "inverse": False,
                },
            },
            {"key": "today_pnl",      "label": "Today P&L", "value": today_pnl, "kind": "currency"},
            {"key": "open_positions", "label": "Open",      "value": 3,         "kind": "number"},
            {"key": "win_rate",       "label": "Win Rate",  "value": 0.62,      "kind": "percent"},
        ],
        "primaryMetricKey": "equity",
    }))


def cmd_activity(args) -> None:
    """Recent events. Sorted newest first by `timestamp`. Each row gets a
    color-coded icon based on `kind` (see PROTOCOL.md §5).
    """
    now = datetime.now(timezone.utc)
    events = []

    # ──────── REPLACE ME ──────────────────────────────────────────────
    # Real implementation: read your service's event log.
    for i in range(min(args.limit, 25)):
        won = random.random() < 0.6
        market = random.choice(SAMPLE_MARKETS)
        pnl = round(random.uniform(5, 90) * (1 if won else -1), 2)
        events.append({
            "id": str(uuid.uuid4()),
            "timestamp": (now - timedelta(hours=i * 2)).isoformat().replace("+00:00", "Z"),
            "kind": "tradeWin" if won else "tradeLoss",
            "title": f"Closed {random.choice(['YES', 'NO'])} on {market['question']}",
            "subtitle": f"Size ${random.randint(20, 500)}",
            "value": pnl,
        })
    # ──────────────────────────────────────────────────────────────────

    print(json.dumps(events))


def cmd_series(args) -> None:
    """Time-series for a given metric. Down-sample on your side; the iOS app
    doesn't. Returns `[{date, value}, ...]`. RANGE is day|week|month|all.
    """
    now = datetime.now(timezone.utc)
    cutoff_hours = {"day": 24, "week": 168, "month": 720, "all": 2160}.get(args.range, 168)
    points = []

    # ──────── REPLACE ME ──────────────────────────────────────────────
    # Real implementation: query your time-series store for the requested
    # (metric, range). Cap point count to ~500 for chart performance.
    if args.metric == "equity":
        value = 11_000.0
        for i in range(cutoff_hours, -1, -1):
            value += random.uniform(-20, 22)
            t = now - timedelta(hours=i)
            points.append({"date": t.isoformat().replace("+00:00", "Z"), "value": round(value, 2)})
    else:
        value = 100.0
        for i in range(cutoff_hours, -1, -1):
            value += random.uniform(-2, 2)
            t = now - timedelta(hours=i)
            points.append({"date": t.isoformat().replace("+00:00", "Z"), "value": round(value, 2)})
    # ──────────────────────────────────────────────────────────────────

    print(json.dumps(points))


# ---------------------------------------------------------------------------
# Commands — the service's own action surface
# ---------------------------------------------------------------------------

def cmd_commands(args) -> None:
    """Declared actions. iOS renders these as tappable buttons. Each tap fires
    `service run NAME --param k=v ...`. See PROTOCOL.md §5 for the schema.
    """
    print(json.dumps([
        {"name": "pause", "label": "Pause",
         "detail": "Halt new entries. Existing state preserved.",
         "systemImage": "pause.fill", "params": [], "dangerous": False},
        {"name": "resume", "label": "Resume",
         "detail": "Re-enable new entries.",
         "systemImage": "play.fill", "params": [], "dangerous": False},
        {"name": "set_max_position", "label": "Set max position",
         "detail": "Update the per-market exposure cap.",
         "systemImage": "slider.horizontal.3",
         "params": [{"name": "amount", "label": "Amount (USD)", "type": "number",
                     "required": True, "placeholder": "500"}],
         "dangerous": False},
        {"name": "flatten", "label": "Flatten all",
         "detail": "Close every open position. Cannot be undone.",
         "systemImage": "arrow.down.to.line", "params": [], "dangerous": True},
        {"name": "test_push", "label": "Test push notification",
         "detail": "Send a test notification to this phone.",
         "systemImage": "bell.badge.fill", "params": [], "dangerous": False},
    ]))


def cmd_run(args) -> None:
    """Dispatch a command. Print `{ok: true, message: "..."}` on success,
    `{error: "..."}` on failure. iOS toasts the message / error.
    """
    state = load_state()
    params = dict(p.split("=", 1) for p in (args.param or []))

    if args.name == "pause":
        state["paused"] = True
        save_state(state)
        _push("Service paused", "New entries halted.", category="control.pause")
        print(json.dumps({"ok": True, "message": "Paused."}))
        return
    if args.name == "resume":
        state["paused"] = False
        save_state(state)
        _push("Service resumed", "Now active.", category="control.resume")
        print(json.dumps({"ok": True, "message": "Resumed."}))
        return
    if args.name == "set_max_position":
        try:
            state["max_position"] = float(params.get("amount", "0"))
            save_state(state)
            print(json.dumps({"ok": True,
                              "message": f"Max position set to ${state['max_position']:,.0f}."}))
            return
        except ValueError:
            print(json.dumps({"error": "Invalid amount."}), file=sys.stderr)
            sys.exit(1)
    if args.name == "flatten":
        _push("Flattened all", "All open positions closed.", category="control.flatten")
        print(json.dumps({"ok": True, "message": "Closed all open positions."}))
        return
    if args.name == "test_push":
        ok = _push("Hello from your service", "If you can read this, push works.",
                   category="control.test")
        print(json.dumps({"ok": ok,
                          "message": "Sent." if ok else "booper-notify not on PATH."}))
        return

    print(json.dumps({"error": f"Unknown command: {args.name}"}), file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Notification categories — surfaces per-category toggles in the iOS app.
# ---------------------------------------------------------------------------

def cmd_notifications(args) -> None:
    """Declare which categories this service can push for. iOS surfaces a
    per-category on/off toggle for each entry. Optional — if you skip this,
    the iOS app auto-discovers categories from incoming pushes (less
    complete; categories only appear after the first push of that type).
    """
    print(json.dumps([
        {"key": "trade.win",      "label": "Trade wins",
         "detail": "Push when a position closes in the green.",
         "systemImage": "checkmark.seal.fill", "defaultEnabled": True},
        {"key": "trade.loss",     "label": "Trade losses",
         "detail": "Push when a position closes in the red.",
         "systemImage": "xmark.octagon.fill",  "defaultEnabled": True},
        {"key": "control.pause",  "label": "Pause / resume",
         "detail": "Push when the service is manually paused or resumed.",
         "systemImage": "pause.circle.fill",   "defaultEnabled": True},
        {"key": "control.flatten","label": "Emergency flatten",
         "detail": "Push when every position is closed at once.",
         "systemImage": "exclamationmark.triangle.fill", "defaultEnabled": True},
    ]))


# ---------------------------------------------------------------------------
# Push notifications — forwards to booper-notify (no APNs key needed here).
# ---------------------------------------------------------------------------

def cmd_register_device(args) -> None:
    """Token registration is handled by booper-notify (installed by the
    watchdog). Forward to it if available; otherwise no-op.
    """
    if _booper_notify_available():
        try:
            subprocess.run(
                ["booper-notify", "register-device", "--token", args.token],
                check=False, timeout=10,
            )
        except Exception:
            pass
    print(json.dumps({"ok": True, "message": "Token forwarded."}))


def cmd_notify(args) -> None:
    """Send a push notification via the booper-notify shim. Include
    --category and --bot-id so the iOS app can apply per-service mute rules.
    """
    ok = _push(args.title, args.body, category=args.category, bot_id=args.bot_id)
    print(json.dumps({
        "ok": ok,
        "message": "Push dispatched." if ok
                   else "booper-notify not on PATH. Install the watchdog from "
                        "the server detail page in Booper.",
    }))


def _push(title: str, body: str, category: str | None = None,
          bot_id: str | None = None) -> bool:
    """Internal helper: fire a push through booper-notify. Returns False if
    the shim isn't installed."""
    if not _booper_notify_available():
        return False
    argv = ["booper-notify", "alert", "--title", title, "--body", body]
    if category:
        argv += ["--category", category]
    if bot_id:
        argv += ["--bot-id", bot_id]
    try:
        subprocess.run(argv, check=False, timeout=15)
        return True
    except Exception:
        return False


def _booper_notify_available() -> bool:
    for prefix in ("/usr/local/bin", "/usr/bin", "/opt/booper/bin"):
        if os.path.exists(os.path.join(prefix, "booper-notify")):
            return True
    return False


# ---------------------------------------------------------------------------
# Trading-only subcommands. Skip these if your service isn't `kind=trading`.
# ---------------------------------------------------------------------------

def cmd_positions(args) -> None:
    """Open positions. Empty array is fine. See PROTOCOL.md for the field
    list — `side` accepts yes/no, y/n, buy/sell, long/short, true/false, 1/0.
    """
    print(json.dumps([
        {"id": str(uuid.uuid4()), "marketId": "us-election-2028",
         "marketQuestion": SAMPLE_MARKETS[0]["question"],
         "side": "yes", "size": 250.00, "entryPrice": 0.42, "currentPrice": 0.48,
         "openedAt": now_iso()},
        {"id": str(uuid.uuid4()), "marketId": "fed-cut-june",
         "marketQuestion": SAMPLE_MARKETS[1]["question"],
         "side": "no", "size": 100.00, "entryPrice": 0.55, "currentPrice": 0.61,
         "openedAt": now_iso()},
    ]))


def cmd_trades(args) -> None:
    """Closed trades. `resolved=false` for pending — win-rate widgets exclude
    them. `pnl` optional: omit and the iOS app computes it from entry/exit
    side-aware.
    """
    now = datetime.now(timezone.utc)
    out = []
    for i in range(min(args.limit, 30)):
        market = random.choice(SAMPLE_MARKETS)
        entry = round(random.uniform(0.30, 0.65), 2)
        won = random.random() < 0.6
        exit_price = round(min(0.98, entry + random.uniform(0.02, 0.18)) if won
                           else max(0.02, entry - random.uniform(0.02, 0.20)), 2)
        out.append({
            "id": str(uuid.uuid4()),
            "marketId": market["id"],
            "marketQuestion": market["question"],
            "side": random.choice(["yes", "no"]),
            "size": round(random.uniform(25, 500), 2),
            "entryPrice": entry,
            "exitPrice": exit_price,
            "closedAt": (now - timedelta(hours=i * 3)).isoformat().replace("+00:00", "Z"),
            "resolved": True,
        })
    print(json.dumps(out))


def cmd_markets(args) -> None:
    """Markets your service trades on. Used for autocomplete-ish surfaces in
    the iOS app.
    """
    print(json.dumps(SAMPLE_MARKETS))


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(prog="service",
                                     description="Booper Reference Service CLI")
    parser.add_argument("--version", action="version", version="booper-service 2.0")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("snapshot")

    p_activity = sub.add_parser("activity")
    p_activity.add_argument("--limit", type=int, default=50)

    p_series = sub.add_parser("series")
    p_series.add_argument("--metric", required=True)
    p_series.add_argument("--range", default="week",
                          choices=["day", "week", "month", "all"])

    sub.add_parser("commands")

    p_run = sub.add_parser("run")
    p_run.add_argument("name")
    p_run.add_argument("--param", action="append",
                       help="Repeated: --param key=value")

    sub.add_parser("notifications")

    sub.add_parser("positions")

    p_trades = sub.add_parser("trades")
    p_trades.add_argument("--limit", type=int, default=50)

    sub.add_parser("markets")

    p_reg = sub.add_parser("register-device",
                           help="Called by Booper to register a phone for push.")
    p_reg.add_argument("--token", required=True)

    p_notify = sub.add_parser("notify",
                              help="Send a push notification.")
    p_notify.add_argument("--title", required=True)
    p_notify.add_argument("--body",  required=True)
    p_notify.add_argument("--category", default=None,
                          help="Notification category key (matches `notifications`).")
    p_notify.add_argument("--bot-id", dest="bot_id", default=None,
                          help="Service identifier — used by the iOS app for per-service mute.")

    args = parser.parse_args()

    handlers = {
        "snapshot":        cmd_snapshot,
        "activity":        cmd_activity,
        "series":          cmd_series,
        "commands":        cmd_commands,
        "run":             cmd_run,
        "notifications":   cmd_notifications,
        "positions":       cmd_positions,
        "trades":          cmd_trades,
        "markets":         cmd_markets,
        "register-device": cmd_register_device,
        "notify":          cmd_notify,
    }

    handlers[args.cmd](args)


if __name__ == "__main__":
    main()
