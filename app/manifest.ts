import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "RTS AI — OpenRA AI Companion",
    short_name: "RTS AI",
    description: "An AI-native OpenRA platform for intelligent play, Earth-built missions, expandable experiences, and autonomous strategy research.",
    start_url: "/",
    scope: "/",
    display: "standalone",
    background_color: "#111411",
    theme_color: "#111411",
    orientation: "any",
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png" },
      { src: "/icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
