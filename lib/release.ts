export type WindowsRelease = {
  version: string;
  url: string;
  checksumUrl: string;
  sizeBytes: number | null;
  publishedAt: string | null;
};

export const fallbackWindowsRelease: WindowsRelease = {
  version: "0.1.0-alpha.8",
  url: "https://github.com/alibad/OpenRA-AI/releases/download/v0.1.0-alpha.8/OpenRA-AI-0.1.0-alpha.8-windows-x64.zip",
  checksumUrl: "https://github.com/alibad/OpenRA-AI/releases/download/v0.1.0-alpha.8/OpenRA-AI-0.1.0-alpha.8-windows-x64.zip.sha256",
  sizeBytes: 81163709,
  publishedAt: "2026-08-08T07:38:26Z",
};

type GitHubRelease = {
  draft: boolean;
  tag_name: string;
  published_at: string | null;
  assets: Array<{
    name: string;
    browser_download_url: string;
    size: number;
  }>;
};

export async function getWindowsRelease(): Promise<WindowsRelease> {
  try {
    const response = await fetch("https://api.github.com/repos/alibad/OpenRA-AI/releases?per_page=20", {
      headers: {
        Accept: "application/vnd.github+json",
        "User-Agent": "rtsai.net",
        "X-GitHub-Api-Version": "2022-11-28",
      },
      next: { revalidate: 900 },
    });
    if (!response.ok) return fallbackWindowsRelease;

    const releases = (await response.json()) as GitHubRelease[];
    for (const release of releases) {
      if (release.draft) continue;
      const archive = release.assets.find((asset) => /windows-x64\.zip$/i.test(asset.name));
      if (!archive) continue;
      const checksum = release.assets.find((asset) => asset.name === `${archive.name}.sha256`);
      return {
        version: release.tag_name.replace(/^v/, ""),
        url: archive.browser_download_url,
        checksumUrl: checksum?.browser_download_url ?? fallbackWindowsRelease.checksumUrl,
        sizeBytes: archive.size,
        publishedAt: release.published_at,
      };
    }
  } catch {
    // The public site must retain a known-good download if GitHub is temporarily unavailable.
  }

  return fallbackWindowsRelease;
}
