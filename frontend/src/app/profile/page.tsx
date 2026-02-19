"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, Save, UserRound } from "lucide-react";
import { toast } from "sonner";

import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/page-header";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch } from "@/lib/api";
import { getAccessToken, getRefreshToken, setAuthSession } from "@/lib/auth";

type DashboardSummary = {
  total_leaves: string;
  leaves_taken: string;
  remaining_balance: string;
};

type MePayload = {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  full_name: string;
  role: string;
  is_admin?: boolean;
  photo_url: string;
  phone_number: string;
  current_project: string;
  project_status: string;
  initiatives_to_take: string;
};

export default function ProfilePage() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [profile, setProfile] = useState<MePayload | null>(null);
  const [photo, setPhoto] = useState<File | null>(null);

  const [phoneNumber, setPhoneNumber] = useState("");
  const [currentProject, setCurrentProject] = useState("");
  const [projectStatus, setProjectStatus] = useState("");
  const [initiatives, setInitiatives] = useState("");

  const photoPreview = useMemo(() => {
    if (photo) return URL.createObjectURL(photo);
    return profile?.photo_url || "";
  }, [photo, profile?.photo_url]);

  async function loadProfile() {
    setLoading(true);
    try {
      const [meResponse, summaryResponse] = await Promise.all([
        apiFetch("/auth/me/"),
        apiFetch("/dashboard/summary/"),
      ]);
      if (!meResponse.ok) throw new Error("Could not load profile");
      const mePayload = (await meResponse.json()) as MePayload;
      setProfile(mePayload);
      setPhoneNumber(mePayload.phone_number || "");
      setCurrentProject(mePayload.current_project || "");
      setProjectStatus(mePayload.project_status || "");
      setInitiatives(mePayload.initiatives_to_take || "");

      if (summaryResponse.ok) {
        const summaryPayload = (await summaryResponse.json()) as DashboardSummary;
        setSummary(summaryPayload);
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not load profile");
    } finally {
      setLoading(false);
    }
  }

  async function saveProfile(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    try {
      const payload = new FormData();
      payload.append("phone_number", phoneNumber);
      payload.append("current_project", currentProject);
      payload.append("project_status", projectStatus);
      payload.append("initiatives_to_take", initiatives);
      if (photo) payload.append("photo", photo);

      const response = await apiFetch("/profile/", {
        method: "PATCH",
        body: payload,
        headers: {},
      });
      if (!response.ok) {
        const body = await response.json();
        throw new Error(body.detail || "Profile update failed");
      }
      const updated = (await response.json()) as MePayload;
      setProfile(updated);
      const access = getAccessToken();
      const refresh = getRefreshToken();
      if (access && refresh) setAuthSession(access, refresh, updated);
      setPhoto(null);
      toast.success("Profile updated");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Profile update failed");
    } finally {
      setSaving(false);
    }
  }

  useEffect(() => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    void loadProfile();
  }, [router]);

  return (
    <AppShell>
      <PageHeader
        title="Profile"
        description="Manage your personal details, project context, and profile photo."
        badge={<Badge variant="outline">My Account</Badge>}
      />

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="surface-card">
          <CardHeader>
            <CardTitle>Profile Card</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {loading ? (
              <div className="flex items-center gap-2 text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Loading...
              </div>
            ) : (
              <>
                <div className="flex items-center gap-3">
                  <Avatar className="h-14 w-14">
                    <AvatarImage src={photoPreview || undefined} />
                    <AvatarFallback>
                      <UserRound className="h-5 w-5" />
                    </AvatarFallback>
                  </Avatar>
                  <div>
                    <p className="font-medium">{profile?.full_name || profile?.username}</p>
                    <p className="text-sm text-muted-foreground">{profile?.email}</p>
                    <p className="text-xs text-primary">{profile?.role}</p>
                  </div>
                </div>
                <div className="grid gap-2 text-sm">
                  <div className="soft-panel">
                    <p className="text-muted-foreground">Total Leaves</p>
                    <p className="font-semibold">{summary?.total_leaves || "0.00"}</p>
                  </div>
                  <div className="soft-panel">
                    <p className="text-muted-foreground">Leaves Taken</p>
                    <p className="font-semibold">{summary?.leaves_taken || "0.00"}</p>
                  </div>
                  <div className="soft-panel">
                    <p className="text-muted-foreground">Remaining Balance</p>
                    <p className="font-semibold">{summary?.remaining_balance || "0.00"}</p>
                  </div>
                </div>
              </>
            )}
          </CardContent>
        </Card>

        <Card className="surface-card lg:col-span-2">
          <CardHeader>
            <CardTitle>Edit Profile</CardTitle>
          </CardHeader>
          <CardContent>
            <form className="grid gap-4" onSubmit={saveProfile}>
              <div className="grid gap-2">
                <Label htmlFor="profile-photo">Profile Photo</Label>
                <Input
                  id="profile-photo"
                  type="file"
                  accept="image/*"
                  onChange={(event) => setPhoto(event.target.files?.[0] || null)}
                />
              </div>
              <div className="grid gap-2 md:grid-cols-2">
                <div className="grid gap-2">
                  <Label htmlFor="phone">Phone Number</Label>
                  <Input id="phone" value={phoneNumber} onChange={(event) => setPhoneNumber(event.target.value)} />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="project">Current Project</Label>
                  <Input id="project" value={currentProject} onChange={(event) => setCurrentProject(event.target.value)} />
                </div>
              </div>
              <div className="grid gap-2">
                <Label htmlFor="status">Project Status</Label>
                <Input id="status" value={projectStatus} onChange={(event) => setProjectStatus(event.target.value)} />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="initiatives">Initiatives To Take</Label>
                <Textarea
                  id="initiatives"
                  rows={4}
                  value={initiatives}
                  onChange={(event) => setInitiatives(event.target.value)}
                />
              </div>
              <Button type="submit" disabled={saving} className="w-full md:w-auto">
                {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
                Save Profile
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </AppShell>
  );
}
