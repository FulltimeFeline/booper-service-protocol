#!/usr/bin/env bash
#
# Booper drop-in service script. Print Booper-Service-Protocol-shaped JSON
# using only standard Unix tools. No Python, no dependencies, no daemon.
#
# Install:
#     curl -fsSL .../snapshot.sh -o /usr/local/bin/service
#     chmod +x /usr/local/bin/service
#
# Then in Booper, add a service pointing to this host with the command
# name `service`. You get a host-metrics dashboard with zero per-service
# code.
#
# This is Tier 1 of the integration ladder. Extend `cmd_snapshot` and
# `cmd_commands` for richer per-service data, or replace it entirely with
# the Python CLI in `reference_service.py` when you outgrow shell.

set -euo pipefail

SUBCOMMAND="${1:-snapshot}"

iso_now() { date -u +%Y-%m-%dT%H:%M:%SZ; }

cmd_snapshot() {
    # Read host stats with portable tools. Linux-specific in places.
    local uptime_seconds load1 mem_total mem_avail mem_used_pct disk_use_pct

    if [[ -r /proc/uptime ]]; then
        uptime_seconds=$(cut -d. -f1 /proc/uptime)
    else
        uptime_seconds=0
    fi

    if [[ -r /proc/loadavg ]]; then
        load1=$(awk '{print $1}' /proc/loadavg)
    else
        load1=0
    fi

    if [[ -r /proc/meminfo ]]; then
        mem_total=$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)
        mem_avail=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)
        if [[ -n "${mem_total:-}" && -n "${mem_avail:-}" && "$mem_total" -gt 0 ]]; then
            mem_used_pct=$(awk -v t="$mem_total" -v a="$mem_avail" 'BEGIN { printf "%.4f", (t - a) / t }')
        else
            mem_used_pct=0
        fi
    else
        mem_used_pct=0
    fi

    disk_use_pct=$(df -P / | awk 'NR==2 {gsub("%",""); printf "%.4f", $5 / 100}')

    cat <<EOF
{
  "online": true,
  "lastSeen": "$(iso_now)",
  "metrics": [
    { "key": "load1",   "label": "Load avg", "value": ${load1},        "kind": "number" },
    { "key": "memory",  "label": "Memory",   "value": ${mem_used_pct}, "kind": "percent",
      "trend": { "delta": 0, "deltaLabel": "now", "direction": "flat", "inverse": true } },
    { "key": "disk",    "label": "Disk /",   "value": ${disk_use_pct}, "kind": "percent",
      "trend": { "delta": 0, "deltaLabel": "now", "direction": "flat", "inverse": true } },
    { "key": "uptime",  "label": "Uptime",   "value": ${uptime_seconds}, "kind": "duration" }
  ],
  "primaryMetricKey": "load1"
}
EOF
}

cmd_activity() {
    # No interesting activity for a generic host — emit an empty array.
    # Replace with `journalctl -n 50 --output=json` or your own log
    # parsing as desired.
    echo "[]"
}

cmd_series() {
    # No historical samples in this stub. Replace with a sqlite/sampler
    # if you want time-series charts to populate.
    echo "[]"
}

cmd_commands() {
    # Pre-baked generic commands. Booper renders these as tappable
    # buttons in the service detail.
    cat <<'EOF'
[
  { "name": "service_status", "label": "Service status",
    "detail": "systemctl status <name>", "systemImage": "waveform.path.ecg",
    "params": [{ "name": "service", "label": "Name", "type": "string", "required": true, "placeholder": "nginx" }],
    "dangerous": false },
  { "name": "service_restart", "label": "Restart service",
    "detail": "systemctl restart <name>", "systemImage": "arrow.clockwise",
    "params": [{ "name": "service", "label": "Name", "type": "string", "required": true, "placeholder": "nginx" }],
    "dangerous": true },
  { "name": "reboot", "label": "Reboot host",
    "detail": "Schedule an immediate reboot.", "systemImage": "power",
    "params": [], "dangerous": true }
]
EOF
}

cmd_run() {
    local name="${2:-}"
    case "$name" in
        service_status)
            local svc
            svc=$(parse_param "$@" service)
            systemctl status "$svc" --no-pager || true
            echo "{ \"ok\": true, \"message\": \"Showed status for ${svc}.\" }"
            ;;
        service_restart)
            local svc
            svc=$(parse_param "$@" service)
            sudo systemctl restart "$svc"
            echo "{ \"ok\": true, \"message\": \"Restarted ${svc}.\" }"
            ;;
        reboot)
            sudo reboot
            ;;
        *)
            echo "{ \"error\": \"Unknown command: ${name}\" }" >&2
            exit 1
            ;;
    esac
}

# Pull `--param key=value` style args.
parse_param() {
    local target="${@: -1}"
    local args=("$@")
    for ((i=0; i<${#args[@]}; i++)); do
        if [[ "${args[i]}" == "--param" && "${args[i+1]}" == "${target}="* ]]; then
            echo "${args[i+1]#${target}=}"
            return
        fi
    done
    echo ""
}

case "$SUBCOMMAND" in
    snapshot)  cmd_snapshot ;;
    activity)  cmd_activity ;;
    series)    cmd_series ;;
    commands)  cmd_commands ;;
    run)       cmd_run "$@" ;;
    --version) echo "booper-service-shell 1.0" ;;
    *)
        echo "Usage: service {snapshot|activity|series|commands|run NAME [--param k=v]}" >&2
        exit 2
        ;;
esac
