import type { MetadataRoute } from "next";

export default function sitemap(): MetadataRoute.Sitemap {
  return [
    {
      url: "https://rtsai.net/",
      lastModified: new Date("2026-08-10"),
      changeFrequency: "weekly",
      priority: 1,
    },
  ];
}
