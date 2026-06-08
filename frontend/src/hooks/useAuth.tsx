import React, { createContext, useContext, useState, useCallback, useEffect } from 'react';

interface AuthState {
  token: string | null;
  isAuthenticated: boolean;
  totpRequired: boolean;
  tempToken: string | null;
}

interface AuthContextType extends AuthState {
  login: (username: string, password: string) => Promise<{ totpRequired: boolean; tempToken?: string }>;
  loginWithTotp: (tempToken: string, totpCode: string) => Promise<void>;
  logout: () => void;
  register: (username: string, password: string) => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

const TOKEN_KEY = 'secureclaw_token';

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>(() => {
    const token = localStorage.getItem(TOKEN_KEY);
    return { token, isAuthenticated: !!token, totpRequired: false, tempToken: null };
  });

  const login = useCallback(async (username: string, password: string) => {
    const res = await fetch('/api/v1/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Login failed' }));
      throw new Error(err.detail || 'Login failed');
    }
    const data = await res.json();
    if (data.totp_required) {
      setState(prev => ({ ...prev, totpRequired: true, tempToken: data.token || '' }));
      return { totpRequired: true, tempToken: data.token };
    }
    localStorage.setItem(TOKEN_KEY, data.token);
    setState({ token: data.token, isAuthenticated: true, totpRequired: false, tempToken: null });
    return { totpRequired: false };
  }, []);

  const loginWithTotp = useCallback(async (tempToken: string, totpCode: string) => {
    const res = await fetch('/api/v1/auth/login/totp', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_token: tempToken, totp_code: totpCode }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'TOTP verification failed' }));
      throw new Error(err.detail || 'TOTP verification failed');
    }
    const data = await res.json();
    localStorage.setItem(TOKEN_KEY, data.token);
    setState({ token: data.token, isAuthenticated: true, totpRequired: false, tempToken: null });
  }, []);

  const register = useCallback(async (username: string, password: string) => {
    const res = await fetch('/api/v1/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Registration failed' }));
      throw new Error(err.detail || 'Registration failed');
    }
    const data = await res.json();
    localStorage.setItem(TOKEN_KEY, data.token);
    setState({ token: data.token, isAuthenticated: true, totpRequired: false, tempToken: null });
  }, []);

  const logout = useCallback(() => {
    const token = state.token;
    if (token) {
      fetch('/api/v1/auth/logout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token }),
      }).catch(() => {});
    }
    localStorage.removeItem(TOKEN_KEY);
    setState({ token: null, isAuthenticated: false, totpRequired: false, tempToken: null });
  }, [state.token]);

  return (
    <AuthContext.Provider value={{ ...state, login, loginWithTotp, logout, register }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextType {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
