#!/bin/sh
set -eu
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
rm -f "$HOME/.local/bin/telechipo" "$HOME/.local/bin/salsilink-control"
rm -f "$DATA_HOME/applications/io.github.gurppt.Telechipo.desktop" "$DATA_HOME/applications/io.github.gurp.Telechipo.desktop" "$DATA_HOME/applications/io.github.gurp.SalsiLinkControl.desktop"
rm -f "$DATA_HOME/icons/hicolor/scalable/apps/io.github.gurppt.Telechipo.svg" "$DATA_HOME/icons/hicolor/scalable/apps/io.github.gurp.Telechipo.svg" "$DATA_HOME/icons/hicolor/scalable/apps/io.github.gurp.SalsiLinkControl.svg"
rm -rf "$DATA_HOME/telechipo" "$DATA_HOME/salsilink-control"
if [ "${1:-}" = "--purge" ]; then
  rm -rf "${XDG_CONFIG_HOME:-$HOME/.config}/telechipo" "${XDG_CONFIG_HOME:-$HOME/.config}/salsilink-control"
  rm -rf "${XDG_STATE_HOME:-$HOME/.local/state}/telechipo" "${XDG_STATE_HOME:-$HOME/.local/state}/salsilink-control"
fi
printf '%s\n' "Telechipo désinstallé. Configuration conservée sauf avec --purge."
