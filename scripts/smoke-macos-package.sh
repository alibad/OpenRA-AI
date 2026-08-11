#!/bin/bash
set -euo pipefail

VERSION="${1:-0.1.0-alpha.1}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPOSITORY_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RELEASE_NAME="OpenRA-AI-$VERSION-macos-arm64"
DMG="$REPOSITORY_ROOT/artifacts/releases/$RELEASE_NAME.dmg"
CHECKSUM="$DMG.sha256"

if [[ "${OSTYPE:-}" != darwin* ]]; then
  echo >&2 "macOS package verification requires a macOS host."
  exit 1
fi

for command in codesign hdiutil shasum; do
  command -v "$command" >/dev/null 2>&1 || { echo >&2 "macOS smoke testing requires $command."; exit 1; }
done
for required in "$DMG" "$CHECKSUM"; do
  [ -f "$required" ] || { echo >&2 "macOS smoke-test input is missing: $required"; exit 1; }
done

expected="$(tr -d '[:space:]' < "$CHECKSUM")"
actual="$(shasum -a 256 "$DMG" | awk '{print $1}')"
[ "$actual" = "$expected" ] || { echo >&2 "DMG checksum does not match."; exit 1; }

mount_root="$(mktemp -d "${TMPDIR:-/tmp}/openra-ai-dmg.XXXXXX")"
cleanup() {
  hdiutil detach "$mount_root" -quiet 2>/dev/null || true
  rmdir "$mount_root" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

hdiutil attach -nobrowse -readonly -mountpoint "$mount_root" "$DMG" >/dev/null
app="$mount_root/OpenRA AI.app"
for required in \
  "$app/Contents/Info.plist" \
  "$app/Contents/MacOS/OpenRAAI" \
  "$app/Contents/MacOS/GameLauncher" \
  "$app/Contents/Resources/bin/openra-ai-companion" \
  "$app/Contents/Resources/packaging/ai-pack.lock.json"; do
  [ -e "$required" ] || { echo >&2 "Mounted app is missing: $required"; exit 1; }
done

codesign --verify --deep --strict "$app"
echo "macOS DMG smoke test passed."
