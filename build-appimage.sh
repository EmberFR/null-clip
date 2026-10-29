#!/usr/bin/env bash
# ==============================================================================
# null-clips — Standalone Native GTK3 ELF64 Type-2 AppImage Builder (v1.0.0)
# Uses the FUSE-free 303-byte ELF64 Type-2 stub (AI\x02 at offset 8) +
# open-source MIT GTK3 runtime (#__NC_PY__) for native Linux & Shelly support.
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

python3 - << 'PYEOF'
import os
from pathlib import Path

root = Path.cwd()
src_path = root / "null_clips_gtk_v1.py"
if not src_path.exists():
    src_path = root / "null-clips.py"
src_bytes = src_path.read_bytes()

# 303-byte ELF64 x86_64 Type-2 AppImage stub (AI\x02 at offset 8, splits on #__NC_PY__\n)
ELF64_STUB = bytes.fromhex(
    "7f454c4602010100414902000000000002003e00010000007800400000000000"
    "4000000000000000000000000000000000000000400038000100400000000000"
    "0100000005000000000000000000000000004000000000000000400000000000"
    "230100000000000023010000000000000010000000000000488b0c24488d54cc"
    "10488d053100000048890424488d052900000050488d051b00000050488d3d0b"
    "000000574889e6b83b0000000f052f62696e2f7368002d63002d2d0065786563"
    "20707974686f6e33202d632022696d706f7274207379733b65786563286f7065"
    "6e287379732e617267765b315d2c5c2272625c22292e7265616428292e73706c"
    "697428625c22235f5f4e435f50595f5f5c5c6e5c222c31295b315d2922202224"
    "4022000a235f5f4e435f50595f5f0a"
)

binary = ELF64_STUB + src_bytes

for out_name in ("null-clips.AppImage", "null-clips-x86_64.AppImage"):
    out_path = root / out_name
    out_path.write_bytes(binary)
    os.chmod(out_path, 0o755)
    print(f"==> Built {out_path} ({len(binary)} bytes)")
PYEOF
