#!/bin/sh
set -u

missing=""

need_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    missing="$missing $1"
    printf '  ✗ %s absent\n' "$1"
    return
  fi
  printf '  ✓ %s : %s\n' "$1" "$(command -v "$1")"
}

printf '%s\n' "Vérification des dépendances de Telechipo :"
need_command python3
need_command adb
need_command scrcpy

gtk_ok=false
if command -v python3 >/dev/null 2>&1 && python3 -c "import gi; gi.require_version('Gtk','4.0'); from gi.repository import Gtk; assert Gtk.get_major_version() >= 4" >/dev/null 2>&1; then
  gtk_ok=true
  printf '%s\n' "  ✓ PyGObject et GTK4"
else
  missing="$missing gtk4-pygobject"
  printf '%s\n' "  ✗ PyGObject/GTK4 absent ou inutilisable"
fi

python_ok=false
if command -v python3 >/dev/null 2>&1 && python3 -c "import sys; raise SystemExit(sys.version_info < (3, 10))" >/dev/null 2>&1; then
  python_ok=true
else
  missing="$missing python>=3.10"
  printf '%s\n' "  ✗ Python 3.10 ou supérieur requis"
fi

if command -v xdotool >/dev/null 2>&1; then
  printf '%s\n' "  ✓ xdotool : mémorisation de la fenêtre scrcpy sous X11"
else
  printf '%s\n' "  ! xdotool absent : seule la mémorisation de position/taille scrcpy sera indisponible"
fi

if [ -z "$missing" ]; then
  printf '%s\n' "Toutes les dépendances obligatoires sont disponibles."
  exit 0
fi

printf '\nDépendances obligatoires manquantes :%s\n' "$missing"
printf '%s\n' "Telechipo ne lance jamais sudo. Commande indicative à vérifier puis exécuter manuellement :"
if command -v apt-get >/dev/null 2>&1; then
  printf '%s\n' "  sudo apt install python3 python3-gi gir1.2-gtk-4.0 adb scrcpy xdotool"
elif command -v dnf >/dev/null 2>&1; then
  printf '%s\n' "  sudo dnf install python3 python3-gobject gtk4 android-tools scrcpy xdotool"
elif command -v pacman >/dev/null 2>&1; then
  printf '%s\n' "  sudo pacman -S python python-gobject gtk4 android-tools scrcpy xdotool"
else
  printf '%s\n' "  Consultez le gestionnaire de paquets de votre distribution pour Python, PyGObject/GTK4, adb, scrcpy et xdotool."
fi
exit 1
