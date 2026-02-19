"use client";

import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, Lock, Mail } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ThemeSelector } from "@/components/theme-selector";
import { API_BASE_URL, readJsonSafely } from "@/lib/api";
import { setAuthSession, type AuthUser } from "@/lib/auth";

function isAuthUser(value: unknown): value is AuthUser {
  if (!value || typeof value !== "object") return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.id === "number" &&
    typeof v.username === "string" &&
    typeof v.email === "string" &&
    typeof v.full_name === "string" &&
    typeof v.role === "string"
  );
}

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch(`${API_BASE_URL}/auth/login/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
        signal: controller.signal,
      });
      const payload = await readJsonSafely<{
        detail?: string;
        access?: string;
        refresh?: string;
        user?: unknown;
      }>(response);
      if (!response.ok) {
        throw new Error(payload?.detail || `Login failed (${response.status})`);
      }
      if (!payload?.access || !payload?.refresh || !isAuthUser(payload.user)) {
        throw new Error("Login API returned an empty or invalid response.");
      }
      setAuthSession(payload.access, payload.refresh, payload.user);
      toast.success("Logged in successfully");
      router.replace("/dashboard");
    } catch (error) {
      const message =
        error instanceof DOMException && error.name === "AbortError"
          ? "Login request timed out. Check backend URL and try again."
          : error instanceof Error
            ? error.message
            : "Login failed";
      toast.error(message);
    } finally {
      clearTimeout(timeout);
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-background px-4 py-10">
      <div className="mx-auto flex w-full max-w-6xl flex-col items-center gap-4">
        <div className="flex w-full justify-end">
          <ThemeSelector />
        </div>
        <Card className="surface-card w-full max-w-md">
          <CardHeader>
            <CardTitle className="text-2xl">Leave Tracker</CardTitle>
            <CardDescription>Sign in with your admin-created account.</CardDescription>
          </CardHeader>
          <CardContent>
            <form className="space-y-4" onSubmit={onSubmit}>
              <div className="space-y-2">
                <Label htmlFor="username">Email or Username</Label>
                <div className="relative">
                  <Mail className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                  <Input
                    id="username"
                    className="pl-9"
                    placeholder="name@company.com"
                    value={username}
                    onChange={(event) => setUsername(event.target.value)}
                    required
                  />
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="password">Password</Label>
                <div className="relative">
                  <Lock className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                  <Input
                    id="password"
                    type="password"
                    className="pl-9"
                    placeholder="Your password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    required
                  />
                </div>
              </div>
              <Button className="w-full" type="submit" disabled={loading}>
                {loading ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Signing in...
                  </>
                ) : (
                  "Login"
                )}
              </Button>
              <div className="text-center text-sm">
                <Link href="/forgot-password" className="text-primary hover:underline">
                  Forgot Password (OTP)
                </Link>
              </div>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
