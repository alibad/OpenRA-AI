import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "./components/AuthProvider";

const geist = Geist({ variable: "--font-geist", subsets: ["latin"] });
const mono = Geist_Mono({ variable: "--font-mono", subsets: ["latin"] });

const canonicalOrigin = new URL("https://rtsai.net");
const title = "RTS AI — OpenRA AI Companion, Earth Missions & Red Sea 2026";
const description =
  "Download OpenRA AI with an interruptible AI companion, optional AUTO command, Earth-built strategy maps, and the Red Sea 2026 prototype.";

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
    "Red Sea 2026",
    "OpenRA mod",
    "Jizan Corridor",
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
        alt: "RTS AI — an OpenRA AI companion, Earth mission generator, and Red Sea 2026 prototype",
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
  return <html lang="en"><body className={`${geist.variable} ${mono.variable}`}><AuthProvider>{children}</AuthProvider></body></html>;
}
