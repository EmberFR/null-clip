# null-clips

**null-clips** is a lightweight, native Linux desktop MP4 replay buffer and game clipper built for Wayland and X11 (`CachyOS`, `Arch Linux`, `Fedora / Nobara`, `Ubuntu / Debian`, `openSUSE`, and `SteamOS`).

---

## Features

- **Zero-Lag GPU Replay Buffer (`15s` / `30s` / `60s` / `120s`)**: Powered by `gpu-screen-recorder` and `ffmpeg` at `60 FPS` or `120 FPS`.
- **Global In-Game Hotkey (`F8` – `F12`)**: Works while tabbed inside fullscreen Wayland & X11 games via Linux kernel input (`evdev`) + compositor bindings.
- **Auto-Detect Game Name in Clip Filenames**: Automatically detects your active game (`Roblox`, `CS2`, `Apex Legends`, `Overwatch 2`, `Minecraft`, `Elden Ring`, `Valorant`, `Helldivers 2`, etc.) and saves clips as `<GameName>_YYYY-MM-DD_HH-MM-SS.mp4`.
- **1-Click Discord Share Link**: Uploads and copies a direct `.mp4` link to your clipboard that embeds inline as a playable video in Discord without Nitro.
- **Built-in Dependency Checker & 1-Click Auto-Installer**: Automatically detects your Linux distro and installs `gpu-screen-recorder`, `ffmpeg`, `wl-clipboard`, and `curl`.
- **Shelly (`Shelly-ALPM`) Ready**: Full AppImage Type-2 compliance (`--appimage-extract`, `--appimage-updateinfo`, desktop entry, and scalable SVG icon).

---

## Installation

### Option 1: Install with Shelly (CachyOS / Arch)

Download **`null-clips.AppImage`** from this repository and open it in **Shelly**, or run:

```bash
shelly install ./null-clips.AppImage
```

### Option 2: Direct AppImage Run

```bash
chmod +x null-clips.AppImage
./null-clips.AppImage
```

### Option 3: Automatic Desktop Installer Script

```bash
chmod +x install.sh
./install.sh
```

---

## License

Copyright (c) 2026 null-clips. **All Rights Reserved.**  
This repository distributes the official prebuilt `null-clips.AppImage` binary release only. Unauthorized copying, redistribution, decompilation, tampering, or reverse engineering is strictly prohibited. See [LICENSE](./LICENSE) for details.
