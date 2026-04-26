#!/usr/bin/env bash
# Yes2All installer / launcher
# Usage: ./install-macos.sh

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

LABEL="com.yes2all.watcher"
MENUBAR_LABEL="com.yes2all.menubar"

# -- status detection ------------------------------------------------------
is_watcher_loaded() {
  local out
  out="$(launchctl list 2>/dev/null || true)"
  echo "$out" | grep -q "$LABEL" && return 0 || return 1
}

is_menubar_loaded() {
  local out
  out="$(launchctl list 2>/dev/null || true)"
  echo "$out" | grep -q "$MENUBAR_LABEL" && return 0 || return 1
}

# -- display ---------------------------------------------------------------
show_menu() {
  printf '\033[H\033[2J\033[3J'

  local w_tag m_tag
  if is_watcher_loaded; then
    w_tag="${GREEN}[installed]${RESET}"
  else
    w_tag="${DIM}[not installed]${RESET}"
  fi
  if is_menubar_loaded; then
    m_tag="${GREEN}[installed]${RESET}"
  else
    m_tag="${DIM}[not installed]${RESET}"
  fi

  local version
  version="$(grep '^version' pyproject.toml | head -1 | sed 's/.*"\(.*\)"/\1/')"
  echo -e "${BOLD}${CYAN}Yes2All${RESET} ${DIM}v${version} — Auto-approve agent tool prompts${RESET}"
  echo ""
  echo -e "  y2a-service: $w_tag"
  echo -e "  y2a-menubar: $m_tag"
  echo ""
  echo -e "    ${YELLOW}0${RESET})  Quick-install y2a-service + y2a-menubar"
  echo ""

  if is_watcher_loaded; then
    echo -e "    ${YELLOW}1${RESET})  Reinstall y2a-service"
    echo -e "    ${YELLOW}2${RESET})  Uninstall y2a-service"
  else
    echo -e "    ${YELLOW}1${RESET})  Install y2a-service"
    echo -e "    ${DIM}2)  Uninstall y2a-service${RESET}"
  fi

  echo ""

  if is_menubar_loaded; then
    echo -e "    ${YELLOW}3${RESET})  Reinstall y2a-menubar"
    echo -e "    ${YELLOW}4${RESET})  Uninstall y2a-menubar"
  else
    echo -e "    ${YELLOW}3${RESET})  Install y2a-menubar"
    echo -e "    ${DIM}4)  Uninstall y2a-menubar${RESET}"
  fi

  echo ""
  echo -e "    ${YELLOW}5${RESET})  Run y2a-service ${DIM}(Ctrl+C to stop)${RESET}"
  echo -e "    ${YELLOW}6${RESET})  Run y2a-menubar ${DIM}(Ctrl+C to stop)${RESET}"
  echo ""
  echo -e "    ${YELLOW}7${RESET})  Show y2a-service status"
  echo ""
  echo -e "    ${YELLOW}9${RESET})  ${RED}Uninstall everything + remove configs and logs${RESET}"
  echo ""
  echo -e "    ${YELLOW}q${RESET})  Quit"
  echo ""
}

prompt_watcher_params() {
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
  read -rsn1 -p "  Choose [0-9/q]: " choice
  echo

  case "$choice" in
    1)
      prompt_watcher_params
      echo ""
      uv run yes2all service install $PORT_ARGS --interval "$INTERVAL" $SWEEP_FLAG --countdown "$COUNTDOWN"
      echo -e "\n  ${GREEN}y2a-service installed.${RESET}"
      pause
      ;;
    2)
      if ! is_watcher_loaded; then
        echo -e "\n  ${DIM}y2a-service is not installed.${RESET}"
      else
        echo ""
        uv run yes2all service uninstall
        echo -e "\n  ${GREEN}y2a-service removed.${RESET}"
      fi
      pause
      ;;
    3)
      echo ""
      uv run yes2all service install-menubar
      echo -e "\n  ${GREEN}y2a-menubar installed.${RESET}"
      pause
      ;;
    4)
      if ! is_menubar_loaded; then
        echo -e "\n  ${DIM}y2a-menubar is not installed.${RESET}"
      else
        echo ""
        uv run yes2all service uninstall-menubar
        echo -e "\n  ${GREEN}y2a-menubar removed.${RESET}"
      fi
      pause
      ;;
    5)
      prompt_watcher_params
      echo -e "\n  ${CYAN}Running y2a-service (Ctrl+C to stop)...${RESET}\n"
      uv run yes2all watch $PORT_ARGS --interval "$INTERVAL" --countdown "$COUNTDOWN" || true
      pause
      ;;
    6)
      echo -e "\n  ${CYAN}Running y2a-menubar (Ctrl+C to stop)...${RESET}\n"
      uv run yes2all menubar || true
      pause
      ;;
    7)
      echo ""
      uv run yes2all service status
      pause
      ;;
    q|Q)
      echo -e "\n  ${DIM}Bye.${RESET}\n"
      exit 0
      ;;
    0)
      echo ""
      uv run yes2all service install --port 9222 --port 9333 --interval 1 --no-sweep-tabs --countdown 3
      echo ""
      uv run yes2all service install-menubar
      echo -e "\n  ${GREEN}y2a-service + y2a-menubar installed.${RESET}"
      pause
      ;;
    9)
      echo ""
      if is_menubar_loaded; then
        uv run yes2all service uninstall-menubar
      fi
      if is_watcher_loaded; then
        uv run yes2all service uninstall
      fi
      rm -rf ~/Library/Application\ Support/yes2all
      rm -rf ~/Library/Logs/yes2all
      echo -e "\n  ${GREEN}Uninstalled. Removed:${RESET}"
      echo -e "    ~/Library/Application Support/yes2all/"
      echo -e "    ~/Library/Logs/yes2all/"
      pause
      ;;
    *)
      echo -e "\n  ${RED}Invalid choice.${RESET}"
      pause
      ;;
  esac
done
