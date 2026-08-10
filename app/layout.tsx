import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geist = Geist({ variable: "--font-geist", subsets: ["latin"] });
const mono = Geist_Mono({ variable: "--font-mono", subsets: ["latin"] });

const canonicalOrigin = new URL("https://rtsai.net");
const title = "RTS AI — AI Companion & Earth Mission Generator for OpenRA";
const description =
  "Download OpenRA AI, play with an interruptible in-game AI companion, and turn real places into validated strategy maps.";

export const metadata: Metadata = {
  metadataBase: canonicalOrigin,
  title,
  description,
  applicationName: "RTS AI",
  category: "games",
  keywords: [
    "RTS AI",
    "OpenRA AI",
    "OpenRA companion",
    "AI strategy game",
    "Earth mission generator",
    "real world strategy maps",
  ],
  alternates: { canonical: "/" },
  manifest: "/manifest.webmanifest",
  referrer: "origin-when-cross-origin",
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      "max-image-preview": "large",
      "max-snippet": -1,
      "max-video-preview": -1,
    },
  },
  icons: {
    icon: [
      { url: "/favicon.ico", sizes: "any" },
      { url: "/favicon-32.png", type: "image/png", sizes: "32x32" },
    ],
    shortcut: "/favicon.ico",
    apple: [{ url: "/apple-touch-icon.png", sizes: "180x180", type: "image/png" }],
  },
  appleWebApp: {
    capable: true,
    title: "RTS AI",
    statusBarStyle: "black-translucent",
  },
  openGraph: {
    title,
    description,
    url: "/",
    siteName: "RTS AI",
    locale: "en_US",
    images: [
      {
        url: "/social-card.png",
        width: 1200,
        height: 630,
        alt: "RTS AI — an AI companion and Earth mission generator for OpenRA",
      },
    ],
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title,
    description,
    images: ["/social-card.png"],
  },
};

export const viewport: Viewport = { themeColor: "#111411", colorScheme: "dark" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body className={`${geist.variable} ${mono.variable}`}>{children}</body></html>;
}
