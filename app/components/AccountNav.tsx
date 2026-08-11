"use client";

import { useState } from "react";
import Image from "next/image";
import { LogOut } from "lucide-react";
import type { User } from "firebase/auth";
import { useAuth } from "./AuthProvider";

export function firebaseProfilePhoto(user: User) {
  return user.photoURL || user.providerData.find((provider) => provider.photoURL)?.photoURL || null;
}

function accountInitials(name: string) {
  const words = name.trim().split(/\s+/).filter(Boolean);
  return (words.length > 1 ? `${words[0][0]}${words.at(-1)?.[0] ?? ""}` : words[0]?.slice(0, 2) || "AI").toUpperCase();
}

function AccountAvatar({ photoUrl, name, large = false }: { photoUrl: string | null; name: string; large?: boolean }) {
  const [failedUrl, setFailedUrl] = useState<string | null>(null);

  const className = `account-avatar${large ? " is-large" : ""}`;
  if (photoUrl && photoUrl !== failedUrl) {
    const size = large ? 40 : 20;
    return <Image unoptimized className={className} src={photoUrl} width={size} height={size} alt="" referrerPolicy="no-referrer" onError={() => setFailedUrl(photoUrl)} />;
  }

  return <span className={`${className} is-fallback`} aria-hidden="true">{accountInitials(name)}</span>;
}

export function AccountNav() {
  const { user, loading, openAuth, signOutUser } = useAuth();

  if (loading) return <span className="nav-account is-loading">Account</span>;
  if (!user) return <button type="button" className="nav-account" onClick={() => openAuth("Sign in to use AI mission generation and companion tools")}>Sign in</button>;

  const displayName = user.displayName?.trim() || user.email?.split("@")[0] || "Commander";
  const firstName = displayName.split(/\s+/)[0];
  const photoUrl = firebaseProfilePhoto(user);
  return (
    <details className="account-menu">
      <summary aria-label={`Open account menu for ${displayName}`}><AccountAvatar photoUrl={photoUrl} name={displayName} /> <span>{firstName}</span></summary>
      <div>
        <div className="account-menu-profile">
          <AccountAvatar photoUrl={photoUrl} name={displayName} large />
          <span><strong>{displayName}</strong><small>{user.email}</small></span>
        </div>
        <button type="button" onClick={() => void signOutUser()}><LogOut size={14} /> Sign out</button>
      </div>
    </details>
  );
}
