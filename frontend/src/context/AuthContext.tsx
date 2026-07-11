/**
 * context/AuthContext.tsx
 *
 * Global auth state. Provides:
 *  - user profile
 *  - login() / logout()
 *  - isAuthenticated flag
 *  - loading state (prevents flash of login page on refresh)
 */
import React, {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  type ReactNode,
} from "react";
import { authApi, type LoginResponse } from "../api/admin";
import { tokenStorage } from "../api/client";

interface AuthUser {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  is_staff: boolean;
  is_superuser: boolean;
}

interface AuthContextValue {
  user: AuthUser | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // On mount: verify existing token and restore session
  useEffect(() => {
    async function restoreSession() {
      const valid = await authApi.verify();
      if (valid) {
        // Token is valid but we need user info — decode from JWT or re-fetch
        // We store user in localStorage on login for quick restore
        const stored = localStorage.getItem("admin_user");
        if (stored) {
          try {
            setUser(JSON.parse(stored));
          } catch {
            tokenStorage.clear();
          }
        }
      } else {
        tokenStorage.clear();
      }
      setIsLoading(false);
    }
    restoreSession();
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const data: LoginResponse = await authApi.login(username, password);
    setUser(data.user);
    localStorage.setItem("admin_user", JSON.stringify(data.user));
  }, []);

  const logout = useCallback(async () => {
    await authApi.logout();
    setUser(null);
    localStorage.removeItem("admin_user");
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: user !== null,
        isLoading,
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}