#!/usr/bin/env bash
set -e

echo "==> Installing null-clips..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APPIMAGE_PATH="$SCRIPT_DIR/null-clips.AppImage"

if [ ! -f "$APPIMAGE_PATH" ]; then
  echo "Error: null-clips.AppImage not found in $SCRIPT_DIR"
  exit 1
fi

chmod +x "$APPIMAGE_PATH"

# If Shelly (Shelly-ALPM) is installed, offer native Shelly installation
if command -v shelly >/dev/null 2>&1; then
  echo "==> Detected Shelly AppImage manager. Installing via Shelly..."
  if shelly install "$APPIMAGE_PATH"; then
    echo "==> Successfully installed null-clips via Shelly!"
    exit 0
  fi
fi

# Standard XDG local installation (~/.local/bin + desktop entry)
mkdir -p "$HOME/.local/bin"
mkdir -p "$HOME/.local/share/applications"
mkdir -p "$HOME/.local/share/icons/hicolor/scalable/apps"

cp "$APPIMAGE_PATH" "$HOME/.local/bin/null-clips.AppImage"
chmod +x "$HOME/.local/bin/null-clips.AppImage"
ln -sf "$HOME/.local/bin/null-clips.AppImage" "$HOME/.local/bin/null-clips"

TMP_EXTRACT="$(mktemp -d)"
(cd "$TMP_EXTRACT" && "$HOME/.local/bin/null-clips.AppImage" --appimage-extract >/dev/null 2>&1 || true)

if [ -f "$TMP_EXTRACT/squashfs-root/null-clips.svg" ]; then
  cp "$TMP_EXTRACT/squashfs-root/null-clips.svg" "$HOME/.local/share/icons/hicolor/scalable/apps/null-clips.svg"
fi

cat > "$HOME/.local/share/applications/null-clips.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=null-clips
GenericName=MP4 Game Clipper
Comment=Lightweight Native Linux MP4 Replay Buffer & Clipper
Exec=$HOME/.local/bin/null-clips.AppImage
Icon=null-clips
Terminal=false
Categories=AudioVideo;Video;Recorder;Utility;
StartupWMClass=null-clips
EOF

rm -rf "$TMP_EXTRACT"
echo "==> Installed null-clips to ~/.local/bin/null-clips and added to your Application Menu!"
