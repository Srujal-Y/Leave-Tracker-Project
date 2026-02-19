"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { CalendarDays, Clock4, Download, Loader2, PlusCircle, ShieldAlert, XCircle } from "lucide-react";
import { toast } from "sonner";

import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiFetch } from "@/lib/api";
import { getAccessToken } from "@/lib/auth";

type LeaveRow = {
  id: number;
  leave_type_name: string;
  start_date: string;
  end_date: string;
  requested_units: string;
  status: string;
  status_label: string;
};

type DashboardSummary = {
  current_year: number;
  total_leaves: string;
  leaves_taken: string;
  remaining_balance: string;
  recent_requests: LeaveRow[];
};

function statusVariant(status: string): "default" | "destructive" | "secondary" | "outline" {
  if (status === "APPROVED") return "default";
  if (status === "REJECTED") return "destructive";
  if (status === "PENDING") return "secondary";
  return "outline";
}

export default function DashboardPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [error, setError] = useState("");

  async function loadSummary() {
    setLoading(true);
    setError("");
    try {
      const response = await apiFetch("/dashboard/summary/");
      if (!response.ok) {
        throw new Error("Could not load dashboard summary");
      }
      const payload = (await response.json()) as DashboardSummary;
      setSummary(payload);
    } catch (fetchError) {
      const message = fetchError instanceof Error ? fetchError.message : "Could not load dashboard";
      setError(message);
    } finally {
      setLoading(false);
    }
  }

  async function cancelRequest(id: number) {
    const response = await apiFetch(`/leave/requests/${id}/`, { method: "DELETE" });
    if (!response.ok && response.status !== 204) {
      let errorMessage = "Could not cancel request";
      try {
        const payload = (await response.json()) as { detail?: string };
        if (payload?.detail) {
          errorMessage = payload.detail;
        }
      } catch {
        // Keep default message for non-JSON responses.
      }
      toast.error(errorMessage);
      return;
    }
    toast.success("Leave request cancelled");
    void loadSummary();
  }

  useEffect(() => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    void loadSummary();
  }, [router]);

  return (
    <AppShell>
      <PageHeader
        title="Employee Dashboard"
        description="Track your leave usage, balances, and request statuses in one place."
        badge={<Badge variant="outline">Overview</Badge>}
        actions={
          <>
            <Button onClick={() => router.push("/leave/apply")}>
              <PlusCircle className="mr-2 h-4 w-4" />
              Apply Leave
            </Button>
            <Button variant="outline" className="bg-card/70" onClick={() => router.push("/company-board")}>
              Company Board
            </Button>
            <Button variant="outline" className="bg-card/70" onClick={() => router.push("/calendar")}>
              Calendar
            </Button>
            <Button
              variant="outline"
              className="bg-card/70"
              onClick={async () => {
                const response = await apiFetch("/leave/ical/", {
                  headers: { Accept: "text/calendar" },
                });
                if (!response.ok) {
                  toast.error("Could not export iCal");
                  return;
                }
                const ics = await response.text();
                const blob = new Blob([ics], { type: "text/calendar;charset=utf-8" });
                const url = URL.createObjectURL(blob);
                const link = document.createElement("a");
                link.href = url;
                link.download = "my-leaves.ics";
                link.click();
                URL.revokeObjectURL(url);
              }}
            >
              <Download className="mr-2 h-4 w-4" />
              Export iCal
            </Button>
          </>
        }
      />

      <section className="grid gap-4 md:grid-cols-3">
        <Card className="metric-card">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Total Leaves ({summary?.current_year || "-"})</CardTitle>
          </CardHeader>
          <CardContent className="text-3xl font-bold tracking-tight">{summary?.total_leaves || "0.00"}</CardContent>
        </Card>
        <Card className="metric-card">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Leaves Taken</CardTitle>
          </CardHeader>
          <CardContent className="text-3xl font-bold tracking-tight">{summary?.leaves_taken || "0.00"}</CardContent>
        </Card>
        <Card className="metric-card">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Remaining Balance</CardTitle>
          </CardHeader>
          <CardContent className="text-3xl font-bold tracking-tight">{summary?.remaining_balance || "0.00"}</CardContent>
        </Card>
      </section>

      <Card className="surface-card">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-xl">
            <CalendarDays className="h-5 w-5 text-primary" />
            Last 5 Leave Requests
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center gap-2 text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading dashboard...
            </div>
          ) : error ? (
            <div className="flex items-center gap-2 text-destructive">
              <ShieldAlert className="h-4 w-4" />
              {error}
            </div>
          ) : (
            <Table className="[&_th]:h-11 [&_th]:text-xs [&_th]:uppercase [&_th]:tracking-wide">
              <TableHeader>
                <TableRow>
                  <TableHead>Type</TableHead>
                  <TableHead>Dates</TableHead>
                  <TableHead>Units</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(summary?.recent_requests || []).length > 0 ? (
                  summary?.recent_requests.map((item) => (
                    <TableRow key={item.id}>
                      <TableCell>{item.leave_type_name}</TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {item.start_date} to {item.end_date}
                      </TableCell>
                      <TableCell>{item.requested_units}</TableCell>
                      <TableCell>
                        <Badge variant={statusVariant(item.status)}>{item.status_label}</Badge>
                      </TableCell>
                      <TableCell className="space-x-2 text-right">
                        {item.status === "PENDING" ? (
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => router.push(`/leave/apply?edit=${item.id}`)}
                          >
                            Edit
                          </Button>
                        ) : null}
                        {item.status === "PENDING" ? (
                          <Button variant="destructive" size="sm" onClick={() => cancelRequest(item.id)}>
                            <XCircle className="mr-1 h-3.5 w-3.5" />
                            Cancel
                          </Button>
                        ) : null}
                      </TableCell>
                    </TableRow>
                  ))
                ) : (
                  <TableRow>
                    <TableCell colSpan={5} className="text-muted-foreground">
                      <div className="soft-panel inline-flex items-center gap-2">
                        <Clock4 className="h-4 w-4" />
                        No leave requests yet.
                      </div>
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </AppShell>
  );
}
