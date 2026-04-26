#!/usr/bin/env bash
# Yes2All installer / launcher (Linux)
# Usage: ./install-linux.sh

set -uo pipefail
cd "$(dirname "$0")"

# -- colors ---------------------------------------------------------------
BOLD='\033[1m'
DIM='\033[2m'
GREEN='\033[32m'
RED='\033[31m'
YELLOW='\033[33m'
CYAN='\033[36m'
RESET='\033[0m'

UNIT="com.yes2all.watcher.service"

# -- status detection ------------------------------------------------------
is_service_active() {
  systemctl --user is-active "$UNIT" &>/dev/null
}

# -- display ---------------------------------------------------------------
show_menu() {
  printf '\033[H\033[2J\033[3J'

  local s_tag
  if is_service_active; then
    s_tag="${GREEN}[running]${RESET}"
  else
    s_tag="${DIM}[not running]${RESET}"
  fi

  local version
  version="$(grep '^version' pyproject.toml | head -1 | sed 's/.*"\(.*\)"/\1/')"
  echo -e "${BOLD}${CYAN}Yes2All${RESET} ${DIM}v${version} — Auto-approve agent tool prompts${RESET}"
  echo ""
  echo -e "  y2a-service: $s_tag"
  echo ""
  echo -e "    ${YELLOW}0${RESET})  Quick-install y2a-service (default settings)"
  echo ""
  echo -e "    ${YELLOW}1${RESET})  Install y2a-service"
  echo -e "    ${YELLOW}2${RESET})  Uninstall y2a-service"
  echo ""
  echo -e "    ${YELLOW}3${RESET})  Run y2a-service ${DIM}(Ctrl+C to stop)${RESET}"
  echo -e "    ${YELLOW}4${RESET})  Show y2a-service status"
  echo ""
  echo -e "    ${YELLOW}5${RESET})  Show CDP targets"
  echo -e "    ${YELLOW}6${RESET})  Probe for approval buttons"
  echo ""
  echo -e "    ${YELLOW}q${RESET})  Quit"
  echo ""
}

prompt_params() {
  echo ""
  read -rp "  Ports (comma-separated) [9222,9333]: " ports_input
  ports_input="${ports_input:-9222,9333}"
  read -rp "  Poll interval (seconds) [1]: " interval
  interval="${interval:-1}"
  read -rp "  Countdown before click (seconds, 0=instant) [3]: " countdown
  countdown="${countdown:-3}"
  read -rp "  Cycle Cursor tabs? [y/N]: " sweep
  sweep="${sweep:-N}"

  PORT_ARGS=""
  IFS=',' read -ra port_arr <<< "$ports_input"
  for p in "${port_arr[@]}"; do
    PORT_ARGS="$PORT_ARGS --port $(echo "$p" | tr -d ' ')"
  done

  SWEEP_FLAG="--no-sweep-tabs"
  if [[ "$sweep" =~ ^[Yy] ]]; then
    SWEEP_FLAG="--sweep-tabs"
  fi

  INTERVAL="$interval"
  COUNTDOWN="$countdown"
}

pause() {
  echo ""
  echo -ne "  ${DIM}Press any key...${RESET}"
  read -rsn1 _
  echo
}

# -- main loop -------------------------------------------------------------
while true; do
  show_menu
  read -rsn1 -p "  Choose [0-6/q]: " choice
  echo

  case "$choice" in
    0)
      echo ""
      uv run yes2all service install --port 9222 --port 9333 --interval 1 --no-sweep-tabs --countdown 3
      echo -e "\n  ${GREEN}y2a-service installed.${RESET}"
      pause
      ;;
    1)
      prompt_params
      echo ""
      uv run yes2all service install $PORT_ARGS --interval "$INTERVAL" $SWEEP_FLAG --countdown "$COUNTDOWN"
      echo -e "\n  ${GREEN}y2a-service installed.${RESET}"
      pause
      ;;
    2)
      if ! is_service_active; then
        echo -e "\n  ${DIM}y2a-service is not running.${RESET}"
      else
        echo ""
        uv run yes2all service uninstall
        echo -e "\n  ${GREEN}y2a-service removed.${RESET}"
      fi
      pause
      ;;
    3)
      prompt_params
      echo -e "\n  ${CYAN}Running y2a-service (Ctrl+C to stop)...${RESET}\n"
      uv run yes2all watch $PORT_ARGS --interval "$INTERVAL" --countdown "$COUNTDOWN" || true
      pause
      ;;
    4)
      echo ""
      uv run yes2all service status
      pause
      ;;
    5)
      echo ""
      read -rp "  Port [9222]: " tport
      tport="${tport:-9222}"
      echo ""
      uv run yes2all targets --port "$tport"
      pause
      ;;
    6)
      echo ""
      read -rp "  Port [9222]: " pport
      pport="${pport:-9222}"
      echo ""
      uv run yes2all probe --port "$pport"
      pause
      ;;
    q|Q)
      echo -e "\n  ${DIM}Bye.${RESET}\n"
      exit 0
      ;;
    *)
      echo -e "\n  ${RED}Invalid choice.${RESET}"
      pause
      ;;
  esac
done
