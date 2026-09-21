"use client";

import Link from "next/link";
import { useAuth } from "@/lib/auth";

export function NavBar() {
  const { token, role, logout, loading } = useAuth();

  return (
    <header className="sticky top-0 z-40 glass">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-4 sm:px-6">
        <Link href="/" className="font-display text-xl font-semibold tracking-tight text-gradient">
          SeatRush
        </Link>
        <nav className="flex items-center gap-2 text-sm sm:gap-4">
          <Link href="/" className="rounded-lg px-3 py-2 text-white/70 transition hover:bg-white/5 hover:text-white">
            Browse
          </Link>
          {!loading && token && (
            <>
              <Link href="/my-bookings" className="rounded-lg px-3 py-2 text-white/70 transition hover:bg-white/5 hover:text-white">
                My Bookings
              </Link>
              {role === "ADMIN" && (
                <Link href="/admin" className="rounded-lg px-3 py-2 text-white/70 transition hover:bg-white/5 hover:text-white">
                  Admin
                </Link>
              )}
              <button onClick={logout} className="rounded-lg border border-border px-3 py-2 text-white/70 transition hover:bg-white/5 hover:text-white">
                Log out
              </button>
            </>
          )}
          {!loading && !token && (
            <Link href="/login" className="rounded-lg bg-accent px-4 py-2 font-medium text-white shadow-glow transition hover:bg-accent-soft">
              Sign in
            </Link>
          )}
        </nav>
      </div>
    </header>
  );
}
