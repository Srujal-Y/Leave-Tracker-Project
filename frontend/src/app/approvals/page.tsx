"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiFetch } from "@/lib/api";
import { getAccessToken, getAuthUser, isAdminOrHR } from "@/lib/auth";

type ApprovalRequest = {
  id: number;
  employee_name: string;
  leave_type_name: string;
  start_date: string;
  end_date: string;
  status: string;
  status_label: string;
};

export default function ApprovalsPage() {
  const router = useRouter();
  const canReview = isAdminOrHR(getAuthUser());
  const [requests, setRequests] = useState<ApprovalRequest[]>([]);
  const [statusFilter, setStatusFilter] = useState("PENDING");
  const [notes, setNotes] = useState<Record<number, string>>({});

  const loadPending = useCallback(async () => {
    const query = statusFilter ? `?status=${statusFilter}` : "";
    const response = await apiFetch(`/leave/requests/${query}`);
    if (!response.ok) {
      toast.error("Could not load approval queue");
      return;
    }
    const payload = (await response.json()) as { results: ApprovalRequest[] };
    setRequests(payload.results || []);
  }, [statusFilter]);

  async function review(id: number, action: "approve" | "reject") {
    const response = await apiFetch(`/leave/requests/${id}/review/`, {
      method: "POST",
      body: JSON.stringify({ action, manager_note: notes[id] || "" }),
    });
    if (!response.ok) {
      toast.error(`Could not ${action} request`);
      return;
    }
    toast.success(`Request ${action}d`);
    setNotes((prev) => ({ ...prev, [id]: "" }));
    void loadPending();
  }

  useEffect(() => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadPending();
  }, [router, loadPending]);

  if (!canReview) {
    return (
      <AppShell>
        <PageHeader
          title="Approval Queue"
          description="Only HR/Admin can review leave requests."
          badge={<Badge variant="outline">Restricted</Badge>}
        />
        <Card className="surface-card">
          <CardHeader>
            <CardTitle>Approval Queue</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">Only HR/Admin can review leave requests.</p>
          </CardContent>
        </Card>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <PageHeader
        title="Approval Queue"
        description="Review pending leave requests, leave notes, and publish decisions."
        badge={<Badge variant="outline">HR / Admin</Badge>}
      />

      <Card className="surface-card">
        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <CardTitle>Approval Queue</CardTitle>
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="w-[180px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="PENDING">Pending</SelectItem>
              <SelectItem value="APPROVED">Approved</SelectItem>
              <SelectItem value="REJECTED">Rejected</SelectItem>
              <SelectItem value="CANCELLED">Cancelled</SelectItem>
            </SelectContent>
          </Select>
        </CardHeader>
        <CardContent>
          <Table className="[&_th]:h-11 [&_th]:text-xs [&_th]:uppercase [&_th]:tracking-wide">
            <TableHeader>
              <TableRow>
                <TableHead>Employee</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Dates</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Manager Note</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {requests.length ? (
                requests.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell>{item.employee_name}</TableCell>
                    <TableCell>{item.leave_type_name}</TableCell>
                    <TableCell>{item.start_date} to {item.end_date}</TableCell>
                    <TableCell>
                      <Badge variant={item.status === "PENDING" ? "secondary" : "default"}>{item.status_label}</Badge>
                    </TableCell>
                    <TableCell className="max-w-64">
                      <Input
                        value={notes[item.id] || ""}
                        onChange={(event) => setNotes((prev) => ({ ...prev, [item.id]: event.target.value }))}
                        placeholder="Optional note"
                        disabled={item.status !== "PENDING"}
                      />
                    </TableCell>
                    <TableCell className="space-x-2 text-right">
                      {item.status === "PENDING" ? (
                        <>
                          <Button size="sm" onClick={() => review(item.id, "approve")}>Approve</Button>
                          <Button size="sm" variant="destructive" onClick={() => review(item.id, "reject")}>Reject</Button>
                        </>
                      ) : (
                        <span className="text-xs text-muted-foreground">No actions</span>
                      )}
                    </TableCell>
                  </TableRow>
                ))
              ) : (
                <TableRow>
                  <TableCell colSpan={6} className="text-muted-foreground">
                    No requests found for selected status.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </AppShell>
  );
}
