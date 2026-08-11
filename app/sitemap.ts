import type { MetadataRoute } from "next";

export default function sitemap(): MetadataRoute.Sitemap {
  const lastModified = new Date("2026-08-11");
  return [
    { url: "https://rtsai.net/", lastModified, changeFrequency: "weekly", priority: 1 },
    { url: "https://rtsai.net/companion", lastModified, changeFrequency: "weekly", priority: 0.9 },
    { url: "https://rtsai.net/studio", lastModified, changeFrequency: "weekly", priority: 0.9 },
    { url: "https://rtsai.net/download", lastModified, changeFrequency: "weekly", priority: 0.9 },
    { url: "https://rtsai.net/platform", lastModified, changeFrequency: "weekly", priority: 0.8 },
    { url: "https://rtsai.net/privacy", lastModified, changeFrequency: "yearly", priority: 0.2 },
  ];
}
