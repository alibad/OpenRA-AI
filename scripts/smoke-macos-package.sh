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

for command in codesign hdiutil otool shasum; do
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

wrapper="$app/Contents/MacOS/OpenRAAI"
/bin/bash -n "$wrapper"
grep -F 'selected_map=""' "$wrapper" >/dev/null || {
  echo >&2 "macOS launcher must open the main menu unless a map is selected."
  exit 1
}
grep -F 'Launch.Bots=Multi1:normal' "$wrapper" >/dev/null || {
  echo >&2 "macOS direct-map launch is missing its default opponent."
  exit 1
}
companion_line="$(grep -n -m1 '^"$companion" watch' "$wrapper" | cut -d: -f1)"
health_line="$(grep -n -m1 '^wait_for_companion_health$' "$wrapper" | cut -d: -f1)"
game_line="$(grep -n -m1 '^"$macos_dir/GameLauncher"' "$wrapper" | cut -d: -f1)"
if [ -z "$companion_line" ] || [ -z "$health_line" ] || [ -z "$game_line" ] || \
  [ "$companion_line" -ge "$health_line" ] || [ "$health_line" -ge "$game_line" ]; then
  echo >&2 "macOS launcher must start the companion, wait for health, and only then start the game."
  exit 1
fi
grep -F -- '--parent-pid "$$"' "$wrapper" >/dev/null || {
  echo >&2 "macOS companion lifecycle must be owned by the launcher wrapper."
  exit 1
}
grep -F 'control_ready' "$wrapper" >/dev/null || {
  echo >&2 "macOS launcher health must require explicit control readiness."
  exit 1
}
for startup_state in \
  OPENRA_AI_COMPANION_READY \
  OPENRA_AI_STARTUP_ENABLED \
  OPENRA_AI_STARTUP_MUTED \
  OPENRA_AI_STARTUP_AUTO_ACT \
  OPENRA_AI_STARTUP_STRATEGY; do
  grep -F "$startup_state" "$wrapper" >/dev/null || {
    echo >&2 "macOS launcher is missing verified startup state: $startup_state"
    exit 1
  }
done
grep -F 'OPENRA_AI_VERSION="$map_version"' "$wrapper" >/dev/null || {
  echo >&2 "macOS companion must receive the exact packaged build version."
  exit 1
}

codesign --verify --deep --strict "$app"
while IFS= read -r library; do
  unsafe_dependencies="$(otool -L "$library" | awk 'NR > 2 && $1 ~ /^\// && $1 !~ /^\/(System\/Library|usr\/lib)\// { print $1 }')"
  if [ -n "$unsafe_dependencies" ]; then
    echo >&2 "Packaged runtime depends on release-host libraries: $library"
    echo >&2 "$unsafe_dependencies"
    exit 1
  fi
done < <(find "$app/Contents/MacOS/arm64" -type f -name '*.dylib' -print)
if codesign -dv --verbose=4 "$app" 2>&1 | grep -q '^Authority=Developer ID Application:'; then
  codesign -d --entitlements - "$app/Contents/MacOS/apphost-arm64" 2>&1 | \
    grep -F 'com.apple.security.cs.allow-jit' >/dev/null || {
      echo >&2 "Developer-ID apphost is missing the .NET JIT entitlement."
      exit 1
    }
fi
"$app/Contents/Resources/bin/openra-ai-companion" voice-check --dependencies-only
echo "macOS DMG smoke test passed."
