#!/bin/bash
set -euo pipefail

VERSION="${1:-0.1.0-alpha.1}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPOSITORY_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENGINE_ROOT="$REPOSITORY_ROOT/engine/openra"
ARTIFACT_ROOT="$REPOSITORY_ROOT/artifacts"
RELEASE_ROOT="$ARTIFACT_ROOT/releases"
PACKAGE_ROOT="$ARTIFACT_ROOT/package/macos"
BRAND_SOURCE="$REPOSITORY_ROOT/assets/brand/rtsai-app-icon.png"
PLIST_TEMPLATE="$REPOSITORY_ROOT/apps/installer/macos/Info.plist.in"
WRAPPER_SOURCE="$REPOSITORY_ROOT/apps/installer/macos/OpenRAAI"
ENTITLEMENTS="$REPOSITORY_ROOT/apps/installer/macos/OpenRAAI.entitlements"
PYTHON="$REPOSITORY_ROOT/.venv/bin/python"
AI_PACK_LOCK="$REPOSITORY_ROOT/packaging/ai-pack.lock.json"
AI_RUNTIME_LOCK="$REPOSITORY_ROOT/packaging/ai-runtime.lock.json"
MODEL_NOTICES="$REPOSITORY_ROOT/packaging/THIRD_PARTY_MODELS.md"
BROTLI_LICENSE="$REPOSITORY_ROOT/packaging/BROTLI-LICENSE.txt"
SAMPLE_MISSION="$REPOSITORY_ROOT/generated/missions/riyadh-crossing-42.oramap"

if [[ "${OSTYPE:-}" != darwin* ]]; then
  echo >&2 "macOS packaging requires a macOS host. The game runtime, .app metadata, DMG, signing, and notarization are verified with Apple tooling."
  exit 1
fi

for command in clang cmake dotnet hdiutil iconutil install_name_tool otool sips shasum; do
  command -v "$command" >/dev/null 2>&1 || { echo >&2 "macOS packaging requires $command."; exit 1; }
done
DOTNET_VERSION="$(dotnet --version)"
if ! [[ "$DOTNET_VERSION" =~ ^([0-9]+)\. ]] || [ "${BASH_REMATCH[1]}" -lt 10 ]; then
  echo >&2 "OpenRA main requires the .NET 10 SDK or newer (found $DOTNET_VERSION)."
  exit 1
fi
if [ -z "${DOTNET_ROOT:-}" ]; then
  DOTNET_RUNTIME_PATH="$(dotnet --list-runtimes | awk 'NR == 1 { gsub(/[\[\]]/, "", $NF); print $NF }')"
  if [[ "$DOTNET_RUNTIME_PATH" == */shared/* ]]; then
    export DOTNET_ROOT="${DOTNET_RUNTIME_PATH%%/shared/*}"
  fi
fi
for required in "$BRAND_SOURCE" "$PLIST_TEMPLATE" "$WRAPPER_SOURCE" "$ENTITLEMENTS" "$PYTHON" "$AI_PACK_LOCK" "$AI_RUNTIME_LOCK" "$MODEL_NOTICES" "$BROTLI_LICENSE"; do
  [ -f "$required" ] || { echo >&2 "macOS packaging input is missing: $required"; exit 1; }
done

"$PYTHON" -m openra_ai_companion.cli voice-check --dependencies-only || {
  echo >&2 "macOS packaging requires the companion voice extra. Run scripts/setup.ps1 again."
  exit 1
}

case "$(uname -m)" in
  arm64)
    RELEASE_ARCH="arm64"
    ARCH_DIR="arm64"
    RUNTIME="osx-arm64"
    CLANG_TARGET="arm64-apple-macos10.15"
    ;;
  x86_64)
    RELEASE_ARCH="x64"
    ARCH_DIR="x86_64"
    RUNTIME="osx-x64"
    CLANG_TARGET="x86_64-apple-macos10.15"
    ;;
  *)
    echo >&2 "Unsupported Mac architecture: $(uname -m)"
    exit 1
    ;;
esac

RELEASE_NAME="OpenRA-AI-$VERSION-macos-$RELEASE_ARCH"
STAGE_ROOT="$PACKAGE_ROOT/$RELEASE_NAME"
APP_ROOT="$STAGE_ROOT/OpenRA AI.app"
CONTENTS="$APP_ROOT/Contents"
MACOS="$CONTENTS/MacOS"
RESOURCES="$CONTENTS/Resources"
DMG="$RELEASE_ROOT/$RELEASE_NAME.dmg"

rm -rf "$STAGE_ROOT"
mkdir -p "$MACOS/$ARCH_DIR" "$RESOURCES/bin" "$RESOURCES/generated/missions" "$RELEASE_ROOT"

source "$ENGINE_ROOT/packaging/functions.sh"
install_assemblies "$ENGINE_ROOT" "$MACOS/$ARCH_DIR" "$RUNTIME" "True" "True" "False"
export OPENRA_AI_UTILITY="$ENGINE_ROOT/bin/$RUNTIME/OpenRA.Utility"

# Homebrew's .NET bottle links its compression shim to Homebrew Brotli. Bundle
# and relocate those libraries when present so the app never depends on the
# release host's package-manager paths.
compression_library="$MACOS/$ARCH_DIR/libSystem.IO.Compression.Native.dylib"
brotli_directory=""
while IFS= read -r dependency; do
  library_name="$(basename "$dependency")"
  brotli_directory="$(dirname "$dependency")"
  cp -L "$dependency" "$MACOS/$ARCH_DIR/$library_name"
  install_name_tool -id "@rpath/$library_name" "$MACOS/$ARCH_DIR/$library_name"
  install_name_tool -change "$dependency" "@loader_path/$library_name" "$compression_library"
done < <(otool -L "$compression_library" | awk 'NR > 2 && $1 ~ /^\/(opt\/homebrew|usr\/local)\/.*libbrotli.*\.dylib$/ { print $1 }')

if [ -n "$brotli_directory" ]; then
  for library in "$MACOS/$ARCH_DIR"/libbrotli*.dylib; do
    while IFS= read -r dependency; do
      library_name="$(basename "$dependency")"
      if [ ! -f "$MACOS/$ARCH_DIR/$library_name" ]; then
        cp -L "$brotli_directory/$library_name" "$MACOS/$ARCH_DIR/$library_name"
        install_name_tool -id "@rpath/$library_name" "$MACOS/$ARCH_DIR/$library_name"
      fi
      install_name_tool -change "$dependency" "@loader_path/$library_name" "$library"
    done < <(otool -L "$library" | awk 'NR > 2 && $1 ~ /libbrotlicommon.*\.dylib$/ { print $1 }')
  done
fi

while IFS= read -r library; do
  unsafe_dependencies="$(otool -L "$library" | awk 'NR > 2 && $1 ~ /^\// && $1 !~ /^\/(System\/Library|usr\/lib)\// { print $1 }')"
  if [ -n "$unsafe_dependencies" ]; then
    echo >&2 "macOS package has non-portable dependencies in $library:"
    echo >&2 "$unsafe_dependencies"
    exit 1
  fi
done < <(find "$MACOS/$ARCH_DIR" -type f -name '*.dylib' -print)

if [ ! -f "$SAMPLE_MISSION" ]; then
  "$PYTHON" -m openra_ai_worldgen.cli generate \
    --lat 24.7136 --lon 46.6753 \
    --title "Riyadh Crossing" --location "Riyadh, Saudi Arabia" \
    --imagery terrain --mode playability-first --seed 42 --offline
fi
"$PYTHON" -m openra_ai_worldgen.cli validate "$SAMPLE_MISSION"

install_data "$ENGINE_ROOT" "$RESOURCES" "ra"
set_engine_version "$VERSION" "$RESOURCES"
set_mod_version "$VERSION" "$RESOURCES/mods/ra/mod.yaml" "$RESOURCES/mods/ra-content/mod.yaml"

clang "$ENGINE_ROOT/packaging/macos/apphost.c" -o "$MACOS/apphost-$ARCH_DIR" -framework AppKit -target "$CLANG_TARGET"
clang "$ENGINE_ROOT/packaging/macos/launcher.m" -o "$MACOS/GameLauncher" -framework AppKit -target "$CLANG_TARGET"

cp "$WRAPPER_SOURCE" "$MACOS/OpenRAAI"
chmod +x "$MACOS/OpenRAAI" "$MACOS/GameLauncher" "$MACOS/apphost-$ARCH_DIR"

BUILD_VERSION="${VERSION%%-*}"
[[ "$BUILD_VERSION" =~ ^[0-9]+(\.[0-9]+){0,2}$ ]] || BUILD_VERSION="1"
sed -e "s|{VERSION}|$VERSION|g" -e "s|{BUILD_VERSION}|$BUILD_VERSION|g" "$PLIST_TEMPLATE" > "$CONTENTS/Info.plist"
echo "APPL????" > "$CONTENTS/PkgInfo"

ICONSET="$PACKAGE_ROOT/rtsai.iconset"
rm -rf "$ICONSET"
mkdir -p "$ICONSET"
sips -z 16 16 "$BRAND_SOURCE" --out "$ICONSET/icon_16x16.png" >/dev/null
sips -z 32 32 "$BRAND_SOURCE" --out "$ICONSET/icon_16x16@2x.png" >/dev/null
sips -z 32 32 "$BRAND_SOURCE" --out "$ICONSET/icon_32x32.png" >/dev/null
sips -z 64 64 "$BRAND_SOURCE" --out "$ICONSET/icon_32x32@2x.png" >/dev/null
sips -z 128 128 "$BRAND_SOURCE" --out "$ICONSET/icon_128x128.png" >/dev/null
sips -z 256 256 "$BRAND_SOURCE" --out "$ICONSET/icon_128x128@2x.png" >/dev/null
sips -z 256 256 "$BRAND_SOURCE" --out "$ICONSET/icon_256x256.png" >/dev/null
sips -z 512 512 "$BRAND_SOURCE" --out "$ICONSET/icon_256x256@2x.png" >/dev/null
sips -z 512 512 "$BRAND_SOURCE" --out "$ICONSET/icon_512x512.png" >/dev/null
cp "$BRAND_SOURCE" "$ICONSET/icon_512x512@2x.png"
iconutil --convert icns "$ICONSET" --output "$RESOURCES/rtsai.icns"
rm -rf "$ICONSET"

SIGNING_IDENTITY="${MACOS_DEVELOPER_IDENTITY:--}"
PYINSTALLER_ARGUMENTS=(
  --noconfirm --clean --onefile
  --name openra-ai-companion
  --paths "$REPOSITORY_ROOT/services/companion/src"
  --collect-all sounddevice
  --collect-data agents
  --distpath "$RESOURCES/bin"
  --workpath "$PACKAGE_ROOT/pyinstaller-work-$RELEASE_ARCH"
  --specpath "$PACKAGE_ROOT/pyinstaller-spec-$RELEASE_ARCH"
)
if [ "$SIGNING_IDENTITY" != "-" ]; then
  PYINSTALLER_ARGUMENTS+=(--codesign-identity "$SIGNING_IDENTITY")
fi
PYINSTALLER_ARGUMENTS+=("$REPOSITORY_ROOT/apps/launcher/companion_entry.py")
"$PYTHON" -m PyInstaller "${PYINSTALLER_ARGUMENTS[@]}"

RUNTIME_PYINSTALLER_ARGUMENTS=(
  --noconfirm --clean --onefile
  --name openra-ai-runtime
  --paths "$REPOSITORY_ROOT/services/companion/src"
  --collect-all kokoro_onnx
  --collect-all espeakng_loader
  --collect-all phonemizer
  --collect-all language_tags
  --distpath "$RESOURCES/bin"
  --workpath "$PACKAGE_ROOT/pyinstaller-work-runtime-$RELEASE_ARCH"
  --specpath "$PACKAGE_ROOT/pyinstaller-spec-runtime-$RELEASE_ARCH"
)
if [ "$SIGNING_IDENTITY" != "-" ]; then
  RUNTIME_PYINSTALLER_ARGUMENTS+=(--codesign-identity "$SIGNING_IDENTITY")
fi
RUNTIME_PYINSTALLER_ARGUMENTS+=("$REPOSITORY_ROOT/apps/launcher/local_ai_entry.py")
"$PYTHON" -m PyInstaller "${RUNTIME_PYINSTALLER_ARGUMENTS[@]}"

"$PYTHON" "$REPOSITORY_ROOT/scripts/ai_pack.py" prepare-runtime \
  --target "macos-$RELEASE_ARCH" \
  --runtime-output "$RESOURCES/ai-runtime"

cp "$SAMPLE_MISSION" "$RESOURCES/generated/missions/"
cp "$REPOSITORY_ROOT/.env.example" "$RESOURCES/"
cp "$REPOSITORY_ROOT/README.md" "$REPOSITORY_ROOT/LICENSE" "$RESOURCES/"
mkdir -p "$RESOURCES/packaging"
cp "$AI_PACK_LOCK" "$AI_RUNTIME_LOCK" "$MODEL_NOTICES" "$BROTLI_LICENSE" "$RESOURCES/packaging/"

sign_runtime_payload() {
  local identity="$1"
  local options=(--force)
  if [ "$identity" = "-" ]; then
    options+=(--timestamp=none)
  else
    options+=(--options runtime --timestamp)
  fi
  while IFS= read -r candidate; do
    if file "$candidate" | grep -q 'Mach-O'; then
      codesign "${options[@]}" --sign "$identity" "$candidate"
    fi
  done < <(find "$RESOURCES/ai-runtime" -type f -print)
}

if [ "$SIGNING_IDENTITY" = "-" ]; then
  sign_runtime_payload -
  codesign --force --timestamp=none --sign - "$RESOURCES/bin/openra-ai-companion"
  codesign --force --timestamp=none --sign - "$RESOURCES/bin/openra-ai-runtime"
  codesign --force --deep --timestamp=none --sign - "$APP_ROOT"
else
  sign_runtime_payload "$SIGNING_IDENTITY"
  codesign --force --options runtime --timestamp --sign "$SIGNING_IDENTITY" "$RESOURCES/bin/openra-ai-companion"
  codesign --force --options runtime --timestamp --sign "$SIGNING_IDENTITY" "$RESOURCES/bin/openra-ai-runtime"
  codesign --force --deep --options runtime --timestamp --sign "$SIGNING_IDENTITY" "$APP_ROOT"
  codesign --force --options runtime --timestamp --entitlements "$ENTITLEMENTS" --sign "$SIGNING_IDENTITY" "$MACOS/apphost-$ARCH_DIR"
  codesign --force --options runtime --timestamp --sign "$SIGNING_IDENTITY" "$APP_ROOT"
  codesign -d --entitlements - "$MACOS/apphost-$ARCH_DIR" 2>/dev/null | grep -F 'com.apple.security.cs.allow-jit' >/dev/null || {
    echo >&2 "The final apphost signature lost the .NET JIT entitlement."
    exit 1
  }
fi

"$RESOURCES/bin/openra-ai-companion" voice-check --dependencies-only || {
  echo >&2 "Signed companion is missing local microphone capture support."
  exit 1
}
"$RESOURCES/bin/openra-ai-runtime" --help >/dev/null || {
  echo >&2 "Signed local AI runtime did not start."
  exit 1
}

rm -f "$DMG" "$DMG.sha256"
hdiutil create -volname "OpenRA AI" -srcfolder "$STAGE_ROOT" -format UDZO -ov "$DMG"
if [ "$SIGNING_IDENTITY" != "-" ]; then
  codesign --force --timestamp --sign "$SIGNING_IDENTITY" "$DMG"
  codesign --verify --strict "$DMG"
fi

NOTARY_PROFILE="${MACOS_NOTARY_PROFILE:-}"
if [ -n "$NOTARY_PROFILE" ] && [ "$SIGNING_IDENTITY" = "-" ]; then
  echo >&2 "MACOS_NOTARY_PROFILE requires MACOS_DEVELOPER_IDENTITY so the submitted DMG is Developer-ID signed."
  exit 1
fi

if [ -n "${MACOS_DEVELOPER_IDENTITY:-}" ]; then
  if [ -n "$NOTARY_PROFILE" ]; then
    NOTARY_ARGUMENTS=(--keychain-profile "$NOTARY_PROFILE")
    if [ -n "${MACOS_NOTARY_KEYCHAIN:-}" ]; then
      NOTARY_ARGUMENTS+=(--keychain "$MACOS_NOTARY_KEYCHAIN")
    fi
    xcrun notarytool submit "$DMG" --wait "${NOTARY_ARGUMENTS[@]}"
    xcrun stapler staple "$DMG"
  elif [ -n "${MACOS_DEVELOPER_TEAM_ID:-}" ] && [ -n "${MACOS_DEVELOPER_USERNAME:-}" ] && [ -n "${MACOS_DEVELOPER_PASSWORD:-}" ]; then
    xcrun notarytool submit "$DMG" --wait \
      --apple-id "$MACOS_DEVELOPER_USERNAME" \
      --password "$MACOS_DEVELOPER_PASSWORD" \
      --team-id "$MACOS_DEVELOPER_TEAM_ID"
    xcrun stapler staple "$DMG"
  fi
fi

shasum -a 256 "$DMG" | awk '{print $1}' > "$DMG.sha256"
printf 'DMG: %s\nSHA-256: %s\n' "$DMG" "$(cat "$DMG.sha256")"
