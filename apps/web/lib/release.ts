export const windowsRelease = {
  version: "0.1.0-alpha.13",
  localAiInstallerDefault: true,
  builtInExperiencePacksDisabledByDefault: true,
  installerUrl: "https://github.com/alibad/OpenRA-AI/releases/download/v0.1.0-alpha.13/OpenRA-AI-0.1.0-alpha.13-windows-x64-setup.exe",
  portableUrl: "https://github.com/alibad/OpenRA-AI/releases/download/v0.1.0-alpha.13/OpenRA-AI-0.1.0-alpha.13-windows-x64.zip",
  aiPackUrl: "https://github.com/alibad/OpenRA-AI/releases/download/v0.1.0-alpha.13/OpenRA-AI-AI-Pack-0.1.0-alpha.13-windows-x64.zip",
  releaseIndexUrl: "https://github.com/alibad/OpenRA-AI/releases/download/v0.1.0-alpha.13/OpenRA-AI-0.1.0-alpha.13-release-index.json",
} as const;

export const macosRelease = {
  version: "0.1.0-alpha.13",
  architecture: "Apple Silicon",
  dmgUrl: "https://github.com/alibad/OpenRA-AI/releases/download/v0.1.0-alpha.13/OpenRA-AI-0.1.0-alpha.13-macos-arm64.dmg",
  checksumUrl: "https://github.com/alibad/OpenRA-AI/releases/download/v0.1.0-alpha.13/OpenRA-AI-0.1.0-alpha.13-macos-arm64.dmg.sha256",
  releaseIndexUrl: "https://github.com/alibad/OpenRA-AI/releases/download/v0.1.0-alpha.13/OpenRA-AI-0.1.0-alpha.13-release-index.json",
} as const;
