#!/usr/bin/env bash
# Build, run and open Netwatch. Usage: ./netwatch.sh {build|start|stop|restart|logs|open|status|install-desktop}
set -euo pipefail

HERE="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
IMAGE="netwatch:latest"
NAME="netwatch"
PORT="${NETWATCH_PORT:-8787}"
URL="http://127.0.0.1:${PORT}"

die() { echo "netwatch: $*" >&2; exit 1; }

check_docker() {
  command -v docker >/dev/null || die "docker is not installed"
  if ! docker info >/dev/null 2>&1; then
    die "can't talk to Docker. Add yourself to the docker group, then log out and back in:
    sudo usermod -aG docker \$USER"
  fi
}

is_running() { [ "$(docker inspect -f '{{.State.Running}}' "$NAME" 2>/dev/null)" = "true" ]; }

build() {
  check_docker
  docker build -t "$IMAGE" "$HERE"
}

start() {
  check_docker
  is_running && { echo "already running at $URL"; return; }
  docker image inspect "$IMAGE" >/dev/null 2>&1 || build
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  # Host networking so the container sees the real Wi-Fi/Ethernet interface;
  # NET_RAW/NET_ADMIN are the only extra privileges, needed for packet capture and ARP.
  docker run -d --name "$NAME" \
    --restart unless-stopped \
    --network host \
    --cap-add NET_RAW --cap-add NET_ADMIN \
    -v netwatch-data:/data \
    -e NETWATCH_PORT="$PORT" \
    ${NETWATCH_IFACE:+-e NETWATCH_IFACE="$NETWATCH_IFACE"} \
    "$IMAGE" >/dev/null
  echo "started; UI at $URL"
}

wait_ready() {
  for _ in $(seq 1 30); do
    curl -fs "$URL/api/status" >/dev/null 2>&1 && return 0
    sleep 0.5
  done
  die "backend didn't come up; check: $0 logs"
}

open_window() {
  # Prefer a Chromium-family browser's --app mode: its own window, no tabs or address bar.
  for b in vivaldi vivaldi-stable chromium chromium-browser google-chrome brave-browser microsoft-edge; do
    if command -v "$b" >/dev/null; then
      nohup "$b" --app="$URL" --class=Netwatch >/dev/null 2>&1 &
      return
    fi
  done
  if command -v flatpak >/dev/null && flatpak info com.microsoft.Edge >/dev/null 2>&1; then
    nohup flatpak run com.microsoft.Edge --app="$URL" >/dev/null 2>&1 &
    return
  fi
  xdg-open "$URL"
}

install_desktop() {
  local apps="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
  mkdir -p "$apps"
  cat > "$apps/netwatch.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Netwatch
Comment=Home network monitor
Exec=$HERE/netwatch.sh open
Icon=$HERE/frontend/public/icon.svg
Terminal=false
Categories=Network;Monitor;
StartupWMClass=Netwatch
DESKTOP
  chmod +x "$apps/netwatch.desktop"
  echo "installed $apps/netwatch.desktop (look for 'Netwatch' in your app menu)"
}

case "${1:-}" in
  build) build ;;
  start) start ;;
  stop) check_docker; docker stop "$NAME" >/dev/null && echo stopped ;;
  restart) check_docker; docker rm -f "$NAME" >/dev/null 2>&1 || true; start ;;
  rebuild) build; check_docker; docker rm -f "$NAME" >/dev/null 2>&1 || true; start ;;
  logs) check_docker; docker logs -f --tail 100 "$NAME" ;;
  status) curl -fs "$URL/api/status" && echo || die "not running" ;;
  open) start; wait_ready; open_window ;;
  install-desktop) install_desktop ;;
  *) echo "usage: $0 {build|start|stop|restart|rebuild|logs|status|open|install-desktop}"; exit 1 ;;
esac
