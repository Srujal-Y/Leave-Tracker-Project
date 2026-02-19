"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, Plus, Save } from "lucide-react";
import { toast } from "sonner";

import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiFetch } from "@/lib/api";
import { getAccessToken, getAuthUser, isAdminOrHR } from "@/lib/auth";

type LeaveType = {
  id: number;
  name: string;
  max_days: number;
  is_paid: boolean;
  active: boolean;
};

type ReasonPreset = {
  id: number;
  label: string;
  active: boolean;
};

export default function LeavePoliciesPage() {
  const router = useRouter();
  const user = getAuthUser();
  const canManage = isAdminOrHR(user);

  const [loading, setLoading] = useState(true);
  const [leaveTypes, setLeaveTypes] = useState<LeaveType[]>([]);
  const [reasonPresets, setReasonPresets] = useState<ReasonPreset[]>([]);

  const [newTypeName, setNewTypeName] = useState("");
  const [newTypeMaxDays, setNewTypeMaxDays] = useState("0");
  const [newTypeIsPaid, setNewTypeIsPaid] = useState(true);
  const [newTypeActive, setNewTypeActive] = useState(true);

  const [newReasonLabel, setNewReasonLabel] = useState("");
  const [newReasonActive, setNewReasonActive] = useState(true);
  const [saving, setSaving] = useState(false);

  async function loadPolicies() {
    setLoading(true);
    try {
      const [typesResponse, reasonsResponse] = await Promise.all([
        apiFetch("/leave/types/"),
        apiFetch("/leave/reasons/"),
      ]);
      if (typesResponse.ok) {
        const typePayload = (await typesResponse.json()) as LeaveType[];
        setLeaveTypes(typePayload);
      }
      if (reasonsResponse.ok) {
        const reasonPayload = (await reasonsResponse.json()) as ReasonPreset[];
        setReasonPresets(reasonPayload);
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not load policies");
    } finally {
      setLoading(false);
    }
  }

  async function createLeaveType() {
    setSaving(true);
    try {
      const response = await apiFetch("/leave/types/", {
        method: "POST",
        body: JSON.stringify({
          name: newTypeName,
          max_days: Number(newTypeMaxDays || "0"),
          is_paid: newTypeIsPaid,
          active: newTypeActive,
        }),
      });
      if (!response.ok) {
        const payload = await response.json();
        throw new Error(payload.detail || "Could not create leave type");
      }
      setNewTypeName("");
      setNewTypeMaxDays("0");
      setNewTypeIsPaid(true);
      setNewTypeActive(true);
      toast.success("Leave type created");
      void loadPolicies();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not create leave type");
    } finally {
      setSaving(false);
    }
  }

  async function createReasonPreset() {
    setSaving(true);
    try {
      const response = await apiFetch("/leave/reasons/", {
        method: "POST",
        body: JSON.stringify({
          label: newReasonLabel,
          active: newReasonActive,
        }),
      });
      if (!response.ok) {
        const payload = await response.json();
        throw new Error(payload.detail || "Could not create reason preset");
      }
      setNewReasonLabel("");
      setNewReasonActive(true);
      toast.success("Reason preset created");
      void loadPolicies();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not create reason preset");
    } finally {
      setSaving(false);
    }
  }

  async function toggleLeaveType(item: LeaveType) {
    const response = await apiFetch(`/leave/types/${item.id}/`, {
      method: "PATCH",
      body: JSON.stringify({ ...item, active: !item.active }),
    });
    if (!response.ok) {
      toast.error("Could not update leave type");
      return;
    }
    toast.success("Leave type updated");
    void loadPolicies();
  }

  async function toggleReason(item: ReasonPreset) {
    const response = await apiFetch(`/leave/reasons/${item.id}/`, {
      method: "PATCH",
      body: JSON.stringify({ label: item.label, active: !item.active }),
    });
    if (!response.ok) {
      toast.error("Could not update reason preset");
      return;
    }
    toast.success("Reason preset updated");
    void loadPolicies();
  }

  useEffect(() => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    void loadPolicies();
  }, [router]);

  if (!canManage) {
    return (
      <AppShell>
        <PageHeader
          title="Leave Policies"
          description="Only HR/Admin can manage leave policy settings."
          badge={<Badge variant="outline">Restricted</Badge>}
        />
        <Card className="surface-card">
          <CardHeader>
            <CardTitle>Leave Policies</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">Only HR/Admin can manage leave policies.</p>
          </CardContent>
        </Card>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <PageHeader
        title="Leave Policies"
        description="Manage leave quotas, paid/unpaid settings, and reason presets."
        badge={<Badge variant="outline">Policy Studio</Badge>}
      />

      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="surface-card">
          <CardHeader>
            <CardTitle>Leave Types</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="soft-panel grid gap-3">
              <div className="space-y-1">
                <Label>Name</Label>
                <Input value={newTypeName} onChange={(event) => setNewTypeName(event.target.value)} placeholder="Annual Leave" />
              </div>
              <div className="space-y-1">
                <Label>Max Days</Label>
                <Input
                  type="number"
                  min={0}
                  value={newTypeMaxDays}
                  onChange={(event) => setNewTypeMaxDays(event.target.value)}
                />
              </div>
              <div className="flex items-center gap-6">
                <label className="flex items-center gap-2 text-sm">
                  <Switch checked={newTypeIsPaid} onCheckedChange={setNewTypeIsPaid} />
                  Paid Leave
                </label>
                <label className="flex items-center gap-2 text-sm">
                  <Switch checked={newTypeActive} onCheckedChange={setNewTypeActive} />
                  Active
                </label>
              </div>
              <Button onClick={createLeaveType} disabled={saving || !newTypeName.trim()}>
                {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Plus className="mr-2 h-4 w-4" />}
                Add Leave Type
              </Button>
            </div>

            <Table className="[&_th]:h-11 [&_th]:text-xs [&_th]:uppercase [&_th]:tracking-wide">
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Max Days</TableHead>
                  <TableHead>Paid</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading ? (
                  <TableRow>
                    <TableCell colSpan={5}>Loading...</TableCell>
                  </TableRow>
                ) : (
                  leaveTypes.map((item) => (
                    <TableRow key={item.id}>
                      <TableCell>{item.name}</TableCell>
                      <TableCell>{item.max_days}</TableCell>
                      <TableCell>{item.is_paid ? "Yes" : "No"}</TableCell>
                      <TableCell>
                        <Badge variant={item.active ? "default" : "secondary"}>{item.active ? "Active" : "Inactive"}</Badge>
                      </TableCell>
                      <TableCell className="text-right">
                        <Button variant="outline" size="sm" onClick={() => toggleLeaveType(item)}>
                          <Save className="mr-2 h-4 w-4" />
                          Toggle
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        <Card className="surface-card">
          <CardHeader>
            <CardTitle>Reason Presets</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="soft-panel grid gap-3">
              <div className="space-y-1">
                <Label>Preset Label</Label>
                <Input value={newReasonLabel} onChange={(event) => setNewReasonLabel(event.target.value)} placeholder="Medical" />
              </div>
              <label className="flex items-center gap-2 text-sm">
                <Switch checked={newReasonActive} onCheckedChange={setNewReasonActive} />
                Active
              </label>
              <Button onClick={createReasonPreset} disabled={saving || !newReasonLabel.trim()}>
                {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Plus className="mr-2 h-4 w-4" />}
                Add Reason Preset
              </Button>
            </div>

            <Table className="[&_th]:h-11 [&_th]:text-xs [&_th]:uppercase [&_th]:tracking-wide">
              <TableHeader>
                <TableRow>
                  <TableHead>Label</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading ? (
                  <TableRow>
                    <TableCell colSpan={3}>Loading...</TableCell>
                  </TableRow>
                ) : (
                  reasonPresets.map((item) => (
                    <TableRow key={item.id}>
                      <TableCell>{item.label}</TableCell>
                      <TableCell>
                        <Badge variant={item.active ? "default" : "secondary"}>{item.active ? "Active" : "Inactive"}</Badge>
                      </TableCell>
                      <TableCell className="text-right">
                        <Button variant="outline" size="sm" onClick={() => toggleReason(item)}>
                          <Save className="mr-2 h-4 w-4" />
                          Toggle
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>
    </AppShell>
  );
}
