#!/usr/bin/env bash
set -euo pipefail

URL="${1:-http://localhost:5173}"
PROFILE_DIR="${XDG_RUNTIME_DIR:-/tmp}/airport-dgpu-browser-profile"
mkdir -p "$PROFILE_DIR"

# Hybrid Linux laptops usually choose the display iGPU for browsers unless the
# browser process itself is launched with PRIME offload hints.
export __NV_PRIME_RENDER_OFFLOAD=1
export __GLX_VENDOR_LIBRARY_NAME=nvidia
export __VK_LAYER_NV_optimus=NVIDIA_only
export DRI_PRIME=1

NVIDIA_RENDER_NODE=""
for vendor_path in /sys/class/drm/renderD*/device/vendor; do
  if [[ -r "$vendor_path" ]] && [[ "$(cat "$vendor_path")" == "0x10de" ]]; then
    node_name="$(basename "$(dirname "$(dirname "$vendor_path")")")"
    NVIDIA_RENDER_NODE="/dev/dri/$node_name"
    break
  fi
done

CHROMIUM_FLAGS=(
  --user-data-dir="$PROFILE_DIR"
  --no-first-run
  --ignore-gpu-blocklist
  --enable-gpu-rasterization
  --ozone-platform=x11
  --disable-vulkan
  --enable-features=CanvasOopRasterization
)

if [[ -n "$NVIDIA_RENDER_NODE" ]]; then
  CHROMIUM_FLAGS+=(--render-node-override="$NVIDIA_RENDER_NODE")
fi

CHROMIUM_CANDIDATES=(
  /snap/brave/current/opt/brave.com/brave/brave
  brave
  brave-browser
  google-chrome-stable
  google-chrome
  chromium
  chromium-browser
)

for browser in "${CHROMIUM_CANDIDATES[@]}"; do
  if [[ "$browser" == /* && -x "$browser" ]]; then
    exec "$browser" "${CHROMIUM_FLAGS[@]}" "$URL"
  fi
  if [[ "$browser" != /* ]] && command -v "$browser" >/dev/null 2>&1; then
    exec "$browser" "${CHROMIUM_FLAGS[@]}" "$URL"
  fi
done

for browser in firefox firefox-developer-edition; do
  if command -v "$browser" >/dev/null 2>&1; then
    exec "$browser" "$URL"
  fi
done

echo "No supported browser executable found. Open $URL in a browser launched with NVIDIA PRIME offload." >&2
exit 1
