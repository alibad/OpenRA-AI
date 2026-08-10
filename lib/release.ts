export type WindowsRelease = {
  version: string;
  url: string;
  checksumUrl: string;
  sizeBytes: number | null;
  publishedAt: string | null;
  installerUrl: string | null;
  installerChecksumUrl: string | null;
  installerSizeBytes: number | null;
};

export type MacOSReleaseAsset = {
  architecture: "arm64" | "x64";
  url: string;
  checksumUrl: string | null;
  sizeBytes: number | null;
};

export type MacOSRelease = {
  version: string;
  publishedAt: string | null;
  assets: MacOSReleaseAsset[];
};

export type GameRelease = {
  windows: WindowsRelease;
  macos: MacOSRelease | null;
};

const releaseBase = "https://github.com/alibad/OpenRA-AI/releases/download/v0.1.0-alpha.8";

export const fallbackWindowsRelease: WindowsRelease = {
  version: "0.1.0-alpha.8",
  url: `${releaseBase}/OpenRA-AI-0.1.0-alpha.8-windows-x64.zip`,
  checksumUrl: `${releaseBase}/OpenRA-AI-0.1.0-alpha.8-windows-x64.zip.sha256`,
  sizeBytes: 81163709,
  publishedAt: "2026-08-08T07:38:26Z",
  installerUrl: `${releaseBase}/OpenRA-AI-0.1.0-alpha.8-windows-x64-setup.exe`,
  installerChecksumUrl: `${releaseBase}/OpenRA-AI-0.1.0-alpha.8-windows-x64-setup.exe.sha256`,
  installerSizeBytes: 63647648,
};

type GitHubAsset = {
  name: string;
  browser_download_url: string;
  size: number;
};

type GitHubRelease = {
  draft: boolean;
  tag_name: string;
  published_at: string | null;
  assets: GitHubAsset[];
};

function checksumFor(asset: GitHubAsset, assets: GitHubAsset[]) {
  return assets.find((candidate) => candidate.name === `${asset.name}.sha256`)?.browser_download_url ?? null;
}

export async function getGameRelease(): Promise<GameRelease> {
  try {
    const response = await fetch("https://api.github.com/repos/alibad/OpenRA-AI/releases?per_page=20", {
      headers: {
        Accept: "application/vnd.github+json",
        "User-Agent": "rtsai.net",
        "X-GitHub-Api-Version": "2022-11-28",
      },
      next: { revalidate: 900 },
    });
    if (!response.ok) return { windows: fallbackWindowsRelease, macos: null };

    const releases = (await response.json()) as GitHubRelease[];
    let windows: WindowsRelease | null = null;
    let macos: MacOSRelease | null = null;

    for (const release of releases) {
      if (release.draft) continue;

      if (!windows) {
        const archive = release.assets.find((asset) => /windows-x64\.zip$/i.test(asset.name));
        if (archive) {
          const installer = release.assets.find((asset) => /windows-x64-setup\.exe$/i.test(asset.name));
          windows = {
            version: release.tag_name.replace(/^v/, ""),
            url: archive.browser_download_url,
            checksumUrl: checksumFor(archive, release.assets) ?? fallbackWindowsRelease.checksumUrl,
            sizeBytes: archive.size,
            publishedAt: release.published_at,
            installerUrl: installer?.browser_download_url ?? null,
            installerChecksumUrl: installer ? checksumFor(installer, release.assets) : null,
            installerSizeBytes: installer?.size ?? null,
          };
        }
      }

      if (!macos) {
        const diskImages = release.assets.filter((asset) => /macos-(arm64|x64)\.dmg$/i.test(asset.name));
        if (diskImages.length) {
          macos = {
            version: release.tag_name.replace(/^v/, ""),
            publishedAt: release.published_at,
            assets: diskImages.map((asset) => ({
              architecture: /macos-arm64\.dmg$/i.test(asset.name) ? "arm64" : "x64",
              url: asset.browser_download_url,
              checksumUrl: checksumFor(asset, release.assets),
              sizeBytes: asset.size,
            })),
          };
        }
      }

      if (windows && macos) break;
    }

    return { windows: windows ?? fallbackWindowsRelease, macos };
  } catch {
    // Keep the known-good Windows downloads visible if GitHub is temporarily unavailable.
    return { windows: fallbackWindowsRelease, macos: null };
  }
}

export async function getWindowsRelease(): Promise<WindowsRelease> {
  return (await getGameRelease()).windows;
}
