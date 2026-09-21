"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { api } from "./api";

type AuthState = {
  token: string | null;
  role: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [role, setRole] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setToken(localStorage.getItem("seatrush_token"));
    setRole(localStorage.getItem("seatrush_role"));
    setLoading(false);
  }, []);

  function persist(t: string, r: string) {
    localStorage.setItem("seatrush_token", t);
    localStorage.setItem("seatrush_role", r);
    setToken(t);
    setRole(r);
  }

  async function login(email: string, password: string) {
    const res = await api.login(email, password);
    persist(res.access_token, res.role);
  }

  async function register(email: string, password: string) {
    const res = await api.register(email, password);
    persist(res.access_token, res.role);
  }

  function logout() {
    localStorage.removeItem("seatrush_token");
    localStorage.removeItem("seatrush_role");
    setToken(null);
    setRole(null);
  }

  return <AuthContext.Provider value={{ token, role, loading, login, register, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
