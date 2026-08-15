"use client";
import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { auth } from "./api";

interface AuthUser {
  id: string;
  email: string;
  full_name: string | null;
}

interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  login: (token: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue>({
  user: null,
  loading: true,
  login: async () => {},
  logout: () => {},
});

function storedToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("token");
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  // Seed from the token's presence rather than defaulting to true and
  // immediately setting false in an effect — a token-less visitor is not
  // "loading", and the effect-then-setState version triggers a cascading render.
  const [loading, setLoading] = useState(() => storedToken() !== null);

  useEffect(() => {
    if (storedToken() === null) return;
    auth
      .me()
      .then(setUser)
      .catch(() => localStorage.removeItem("token"))
      .finally(() => setLoading(false));
  }, []);

  const login = async (token: string) => {
    localStorage.setItem("token", token);
    setUser(await auth.me());
  };

  const logout = () => {
    localStorage.removeItem("token");
    setUser(null);
    window.location.assign("/login");
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
