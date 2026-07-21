# Telechipo

Telechipo est une petite interface GTK4 pour connecter un téléphone Android avec ADB Wi-Fi et lancer scrcpy. Elle gère plusieurs téléphones, mémorise leurs réglages et supervise la fenêtre native de scrcpy.

## Installation

Clonez le dépôt puis lancez le script utilisateur :

```bash
git clone https://github.com/gurppt/telechipo.git
cd telechipo
./scripts/install-user.sh
```

Le script vérifie les dépendances avant toute modification. Il n’utilise jamais `sudo` et n’installe rien automatiquement. Si un composant manque, il affiche une commande adaptée à `apt`, `dnf` ou `pacman`.

Une fois installé, lancez **Telechipo** depuis le menu des applications ou avec :

```bash
telechipo
```

### Dépendances

- Python 3.10 ou supérieur ;
- GTK4 et PyGObject ;
- `adb` ;
- `scrcpy` ;
- `xdotool`, facultatif mais nécessaire pour mémoriser la taille et la position de la fenêtre scrcpy sous X11.

Exemples de commandes, à vérifier selon la version de votre distribution :

```bash
# Debian, Ubuntu, Pop!_OS
sudo apt install python3 python3-gi gir1.2-gtk-4.0 adb scrcpy xdotool

# Fedora
sudo dnf install python3 python3-gobject gtk4 android-tools scrcpy xdotool

# Arch Linux
sudo pacman -S python python-gobject gtk4 android-tools scrcpy xdotool
```

Vous pouvez lancer uniquement le diagnostic avec :

```bash
./scripts/check-dependencies.sh
```

## Utilisation

Pour préparer un téléphone la première fois :

1. activez le débogage USB sur Android ;
2. branchez et déverrouillez le téléphone ;
3. acceptez l’autorisation ADB ;
4. créez ou sélectionnez son profil dans Telechipo ;
5. cliquez sur **Préparer Wi-Fi**.

Vous pouvez ensuite retirer le câble. Tant qu’ADB TCP/IP reste actif et que l’adresse du téléphone ne change pas, utilisez **Connecter**, puis **Afficher**. Une réservation DHCP est recommandée. Après un redémarrage complet du téléphone, il peut être nécessaire de refaire la préparation USB.

Chaque profil conserve son adresse, son port, ses réglages vidéo et la géométrie de sa fenêtre scrcpy. Telechipo détecte dynamiquement les options disponibles afin de fonctionner avec les anciennes et nouvelles versions de scrcpy.

## Mise à jour

```bash
cd telechipo
git pull
./scripts/install-user.sh
```

Les profils existants sont conservés dans `~/.config/telechipo/config.json`.

## Désinstallation

```bash
./scripts/uninstall-user.sh
```

La configuration est conservée. Pour supprimer également les profils :

```bash
./scripts/uninstall-user.sh --purge
```

## Développement

Lancement sans installation :

```bash
PYTHONPATH=src python3 -m salsilink_control
```

Tests sans téléphone :

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Telechipo cible principalement Linux/X11. Sous Wayland, adb et scrcpy fonctionnent normalement, mais le compositeur contrôle le placement des fenêtres.

Licence MIT.
