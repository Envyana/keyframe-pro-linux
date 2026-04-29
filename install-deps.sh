#!/usr/bin/env bash
# Detect distro and install system deps required by python-mpv (libmpv) and Qt.
set -e

# Don't run the whole script as root — only `apt install` etc. need sudo.
# If run as root, the .venv would end up owned by root and pip wouldn't be
# usable from the user account afterwards.
if [ "$(id -u)" = "0" ]; then
    cat >&2 <<'EOF'
ERROR: Run this script as your normal user, NOT with sudo / as root.
The script will call `sudo` itself only for the apt/dnf/etc. install step.
Running the whole script as root makes the Python venv owned by root.

Correct:    ./install-deps.sh
Wrong:      sudo ./install-deps.sh
            sudo sh ./install-deps.sh
EOF
    exit 1
fi

if [ -f /etc/os-release ]; then
    . /etc/os-release
    DISTRO="${ID:-unknown}"
    DISTRO_LIKE="${ID_LIKE:-}"
else
    DISTRO="unknown"
    DISTRO_LIKE=""
fi

echo "Detected distro: $DISTRO ($DISTRO_LIKE)"

case "$DISTRO" in
    ubuntu|debian|linuxmint|pop|elementary|zorin|kali|raspbian)
        sudo apt update
        # libmpv package name differs by version:
        #   Ubuntu 22.04 (jammy) / Pop!_OS 22.04 / Debian bookworm → libmpv1
        #   Ubuntu 24.04 (noble) / Debian trixie+               → libmpv2
        if apt-cache show libmpv2 >/dev/null 2>&1; then
            LIBMPV_PKG="libmpv2"
        elif apt-cache show libmpv1 >/dev/null 2>&1; then
            LIBMPV_PKG="libmpv1"
        else
            echo "Could not find libmpv1 or libmpv2 in apt. Add a backport or build libmpv from source."
            exit 1
        fi
        echo "Using libmpv package: $LIBMPV_PKG"
        sudo apt install -y python3 python3-venv python3-pip "$LIBMPV_PKG" mpv ffmpeg \
            libxkbcommon-x11-0 libxcb-cursor0 libegl1
        ;;
    fedora)
        sudo dnf install -y python3 python3-pip mpv mpv-libs ffmpeg \
            libxkbcommon-x11 xcb-util-cursor mesa-libEGL
        ;;
    silverblue|kinoite|fedora-silverblue|fedora-kinoite)
        echo "Detected immutable Fedora (Silverblue/Kinoite)."
        echo "Two recommended approaches:"
        echo "  1) Layer system deps via rpm-ostree (requires reboot):"
        echo "       rpm-ostree install mpv mpv-libs ffmpeg python3-pip"
        echo "  2) Use a toolbox/distrobox (recommended, no reboot):"
        echo "       toolbox create --image registry.fedoraproject.org/fedora-toolbox:latest"
        echo "       toolbox enter"
        echo "       sudo dnf install -y python3 python3-pip mpv mpv-libs ffmpeg \\"
        echo "         libxkbcommon-x11 xcb-util-cursor mesa-libEGL"
        echo "Run this script inside the toolbox/distrobox if you go with option 2."
        exit 0
        ;;
    arch|manjaro|endeavouros)
        sudo pacman -Sy --needed python python-pip mpv ffmpeg \
            libxkbcommon-x11 xcb-util-cursor
        ;;
    opensuse*|sles)
        sudo zypper install -y python3 python3-pip mpv libmpv2 ffmpeg \
            libxkbcommon-x11-0 libxcb-cursor0
        ;;
    *)
        case "$DISTRO_LIKE" in
            *debian*) sudo apt update && sudo apt install -y python3 python3-venv python3-pip libmpv2 mpv ffmpeg ;;
            *fedora*) sudo dnf install -y python3 python3-pip mpv mpv-libs ffmpeg ;;
            *arch*)   sudo pacman -Sy --needed python python-pip mpv ffmpeg ;;
            *)
                echo "Unsupported distro. Install manually:"
                echo "  - python3 (>=3.10), pip, venv"
                echo "  - libmpv (>=0.34) and ffmpeg"
                echo "  - libxkbcommon, xcb-cursor, EGL"
                exit 1
                ;;
        esac
        ;;
esac

echo
echo "System deps installed. Now setting up Python venv..."
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
echo
echo "Done. To run:"
echo "  source .venv/bin/activate"
echo "  python -m keyframe_pro            # GUI"
echo "  python -m keyframe_pro file.mp4   # open a video on launch"
