"use client";

import { LogOut, UserRound } from "lucide-react";
import { useAuth } from "./AuthProvider";

export function AccountNav() {
  const { user, loading, openAuth, signOutUser } = useAuth();

  if (loading) return <span className="nav-account is-loading">Account</span>;
  if (!user) return <button type="button" className="nav-account" onClick={() => openAuth("Sign in to use AI mission generation and companion tools")}>Sign in</button>;

  const firstName = user.displayName?.trim().split(/\s+/)[0] || "Commander";
  return (
    <details className="account-menu">
      <summary><UserRound size={15} /> {firstName}</summary>
      <div>
        <strong>{user.displayName || "Commander"}</strong>
        <small>{user.email}</small>
        <button type="button" onClick={() => void signOutUser()}><LogOut size={14} /> Sign out</button>
      </div>
    </details>
  );
}
