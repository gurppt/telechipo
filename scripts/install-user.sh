#!/bin/sh
set -eu
PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
"$PROJECT_DIR/scripts/check-dependencies.sh"
APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/telechipo"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ICON_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps"
mkdir -p "$APP_DIR" "$BIN_DIR" "$DESKTOP_DIR" "$ICON_DIR"
cp -R "$PROJECT_DIR/src" "$PROJECT_DIR/pyproject.toml" "$APP_DIR/"
cp "$PROJECT_DIR/data/io.github.gurppt.Telechipo.desktop" "$DESKTOP_DIR/"
cp "$PROJECT_DIR/icon/sausage-svgrepo-com.svg" "$ICON_DIR/io.github.gurppt.Telechipo.svg"
cat > "$BIN_DIR/telechipo" <<EOF
#!/bin/sh
export PYTHONPATH="$APP_DIR/src\${PYTHONPATH:+:\$PYTHONPATH}"
exec python3 -m salsilink_control "\$@"
EOF
chmod 755 "$BIN_DIR/telechipo"
# Remove launchers from versions older than the Telechipo rename.
rm -f "$BIN_DIR/salsilink-control" "$DESKTOP_DIR/io.github.gurp.SalsiLinkControl.desktop" "$ICON_DIR/io.github.gurp.SalsiLinkControl.svg"
rm -f "$DESKTOP_DIR/io.github.gurp.Telechipo.desktop" "$ICON_DIR/io.github.gurp.Telechipo.svg"
rm -rf "${XDG_DATA_HOME:-$HOME/.local/share}/salsilink-control"
# Ask desktop environments to notice an icon replacement immediately when the
# cache updater is available. Other environments refresh it automatically.
if command -v gtk4-update-icon-cache >/dev/null 2>&1; then
  gtk4-update-icon-cache -f -t "${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor" >/dev/null 2>&1 || true
elif command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -f -t "${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor" >/dev/null 2>&1 || true
fi
printf '%s\n' "Telechipo installé pour l’utilisateur."
