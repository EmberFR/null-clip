# null-clips (v1.0.0)

Open-source native Linux GPU replay buffer & H.264 `.mp4` game clipper built with **GTK3 + Cairo**, a zero-overhead **C daemon**, [`gpu-screen-recorder`](https://git.dec05eba.com/gpu-screen-recorder), and `ffmpeg`. Designed for Wayland (Hyprland, Sway, KDE Plasma, GNOME) and X11 with near-zero RAM/VRAM overhead (`0 MB` when idle in Game-Only mode, `~1.2 MB` for the C daemon).

## Key Features (v1.0.0)

- **Native GTK3 + Cairo Desktop App & C Daemon**: Zero Electron/CEF/web-companion bloat. Runs natively on Wayland & X11.
- **Zero-Copy GPU Replay Buffer (`gpu-screen-recorder`)**: Keeps the last `15s` / `30s` / `60s` / `120s` in a hardware-encoded H.264 ring buffer and saves an `.mp4` on your custom hotkey (`SIGUSR1`).
- **Game-Only Buffer (0 MB Idle Mode) & Auto-Cleanup Cap**: Optional toggle that pauses `gpu-screen-recorder` until a Steam/Proton or native game is detected, plus an automatic folder size cap (`5 GB` – `100 GB`) that prunes oldest clips when full.
- **Click-to-Bind Custom Keybind Recorder**: Click the keybind button in Settings and press any key (`F8`, `F9`, `Insert`, `Print`, etc.) to bind your global save hotkey.
- **Async 64×36 Clip Thumbnails & Per-Game Auto-Tagging**: Generates lightweight cached thumbnails in `/tmp/null-clips-thumbs` and tags clips by active game (`CS2`, `Roblox`, `ApexLegends`, `EldenRing`, etc.).
- **Dual-Track Audio Mixer & Target Size Export (`< 10MB` / `< 25MB` / `< 50MB` / `Lossless`)**: Adjust Desktop and Mic track volumes independently and encode to fit Discord upload limits or use instant lossless stream copy (`-c copy`).

---

## 1. System Dependencies

### Arch Linux / CachyOS / EndeavourOS
```bash
sudo pacman -S --needed gpu-screen-recorder ffmpeg wl-clipboard curl python python-gobject gtk3
```

### Fedora / Nobara
```bash
sudo dnf install -y gpu-screen-recorder ffmpeg wl-clipboard curl python3 python3-gobject gtk3
```

### Ubuntu / Debian / Pop!_OS
```bash
sudo apt-get update && sudo apt-get install -y ffmpeg wl-clipboard curl python3 python3-gi python3-gi-cairo gir1.2-gtk-3.0
```

---

## 2. Run or Install from Source

### Option A: Run Directly with Python 3
```bash
git clone https://github.com/EmberFR/null-clip.git
cd null-clip
chmod +x null-clips.py
./null-clips.py
```

### Option B: Local Desktop Installer (`./install.sh`)
```bash
git clone https://github.com/EmberFR/null-clip.git
cd null-clip
chmod +x install.sh
./install.sh
```

### Option C: Arch Linux / CachyOS (`PKGBUILD`)
```bash
git clone https://github.com/EmberFR/null-clip.git
cd null-clip
makepkg -si
```

---

## 3. Build Standalone ELF64 `.AppImage` from Source

To package `null-clips.AppImage` (`~88 KB`, FUSE-free ELF64 Type-2 header + embedded open-source GTK3 runtime, compatible with Shelly and Linux app launchers):

```bash
chmod +x build-appimage.sh
./build-appimage.sh
./null-clips.AppImage
```

---

## Source Architecture

- `null-clips.py` / `null_clips_gtk_v1.py` — Native GTK3 + Cairo desktop UI, interactive trim timeline, dual-track audio mixer, async 64×36 thumbnail generator, Game-Only buffer watchdog, and Discord uploader.
- `null_clips_daemon.c` — Lightweight C hotkey & replay daemon (~1.2 MB RSS).
- `build-appimage.sh` — FUSE-free ELF64 Type-2 `.AppImage` builder.
- `install.sh` — Local desktop entry and icon installer.
- `PKGBUILD` — Arch Linux / CachyOS package specification.

## License

MIT License — see [LICENSE](./LICENSE).
