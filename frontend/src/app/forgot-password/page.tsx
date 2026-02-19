"use client";

import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, Mail, ShieldCheck } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { API_BASE_URL } from "@/lib/api";

export default function ForgotPasswordPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [token, setToken] = useState("");
  const [debugOtp, setDebugOtp] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setDebugOtp("");
    try {
      const response = await fetch(`${API_BASE_URL}/auth/password-reset/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || "Could not send OTP");
      }
      setToken(payload.token || "");
      setDebugOtp(payload.debug_otp || "");
      toast.success(payload.message || "OTP sent to your email");
      if (payload.token) {
        router.push(`/forgot-password/verify/${payload.token}`);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "Could not send OTP";
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="tinted-grid-bg min-h-screen bg-background px-4 py-10">
      <div className="mx-auto flex w-full max-w-5xl items-center justify-center">
        <Card className="surface-card w-full max-w-md">
          <CardHeader>
            <CardTitle className="text-2xl">Forgot Password</CardTitle>
            <CardDescription>Enter your email to receive a 6-digit OTP.</CardDescription>
          </CardHeader>
          <CardContent>
            <form className="space-y-4" onSubmit={onSubmit}>
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <div className="relative">
                  <Mail className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                  <Input
                    id="email"
                    className="pl-9"
                    type="email"
                    placeholder="name@company.com"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    required
                  />
                </div>
              </div>
              <Button className="w-full" type="submit" disabled={loading}>
                {loading ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Sending OTP...
                  </>
                ) : (
                  "Send OTP"
                )}
              </Button>
              {debugOtp ? (
                <div className="rounded-md border border-primary/40 bg-primary/10 p-3 text-sm">
                  <p className="inline-flex items-center gap-2 font-medium">
                    <ShieldCheck className="h-4 w-4" />
                    Dev Mode OTP
                  </p>
                  <p className="mt-1 text-muted-foreground">Use this OTP from console backend: <strong>{debugOtp}</strong></p>
                </div>
              ) : null}
              {token ? (
                <div className="rounded-md border border-dashed p-3 text-sm">
                  <p className="text-muted-foreground">If redirect didn’t happen, continue manually:</p>
                  <Link href={`/forgot-password/verify/${token}`} className="text-primary hover:underline">
                    Open OTP verification
                  </Link>
                </div>
              ) : null}
              <div className="text-center text-sm">
                <Link href="/login" className="text-primary hover:underline">
                  Back to Login
                </Link>
              </div>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
