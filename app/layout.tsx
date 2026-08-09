import type { Metadata, Viewport } from "next";
import { headers } from "next/headers";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geist = Geist({ variable: "--font-geist", subsets: ["latin"] });
const mono = Geist_Mono({ variable: "--font-mono", subsets: ["latin"] });

export async function generateMetadata(): Promise<Metadata> {
  const requestHeaders = await headers();
  const host = requestHeaders.get("x-forwarded-host") ?? requestHeaders.get("host") ?? "localhost:3000";
  const protocol = requestHeaders.get("x-forwarded-proto") ?? (host.startsWith("localhost") ? "http" : "https");
  const origin = new URL(`${protocol}://${host}`);
  return {
    metadataBase: origin,
    title: "RTS AI — Your battlefield, now it talks back",
    description: "Download OpenRA AI, use its interruptible game companion, and turn real locations into playable strategy maps.",
    icons: { icon: "/favicon.svg", shortcut: "/favicon.svg" },
    openGraph: {
      title: "RTS AI — Your battlefield, now it talks back",
      description: "A quiet AI companion and a map generator that turns any place on Earth into a playable skirmish.",
      url: origin,
      siteName: "RTS AI",
      images: [{ url: "/og.png", width: 1536, height: 1024, alt: "RTS AI tactical world map" }],
      type: "website",
    },
    twitter: { card: "summary_large_image", title: "RTS AI", description: "Your battlefield, now it talks back.", images: ["/og.png"] },
  };
}

export const viewport: Viewport = { themeColor: "#111411", colorScheme: "dark" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body className={`${geist.variable} ${mono.variable}`}>{children}</body></html>;
}
