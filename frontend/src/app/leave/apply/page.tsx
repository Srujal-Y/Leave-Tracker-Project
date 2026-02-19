"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Loader2, Paperclip, Send } from "lucide-react";
import { toast } from "sonner";

import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch } from "@/lib/api";
import { getAccessToken } from "@/lib/auth";

type LeaveType = {
  id: number;
  name: string;
  max_days: number;
};

const MAX_TOTAL_DOC_BYTES = 10 * 1024 * 1024 * 1024;

function ApplyLeavePageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const editId = searchParams.get("edit");
  const [leaveTypes, setLeaveTypes] = useState<LeaveType[]>([]);
  const [loadingTypes, setLoadingTypes] = useState(true);
  const [loadingExisting, setLoadingExisting] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [leaveType, setLeaveType] = useState("");
  const [leaveLabel, setLeaveLabel] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [portion, setPortion] = useState("FULL");
  const [reasonText, setReasonText] = useState("");
  const [files, setFiles] = useState<File[]>([]);

  useEffect(() => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }

    async function loadLeaveTypes() {
      setLoadingTypes(true);
      try {
        const response = await apiFetch("/leave/types/");
        if (!response.ok) throw new Error("Unable to load leave types");
        const payload = (await response.json()) as LeaveType[];
        setLeaveTypes(payload);
      } catch (error) {
        toast.error(error instanceof Error ? error.message : "Failed to load leave types");
      } finally {
        setLoadingTypes(false);
      }
    }

    void loadLeaveTypes();
  }, [router]);

  useEffect(() => {
    if (!editId) return;
    async function loadExisting() {
      setLoadingExisting(true);
      try {
        const response = await apiFetch(`/leave/requests/${editId}/`);
        if (!response.ok) throw new Error("Could not load request for edit");
        const payload = (await response.json()) as {
          leave_type: number;
          leave_label: string;
          start_date: string;
          end_date: string;
          portion: string;
          reason_text: string;
        };
        setLeaveType(String(payload.leave_type));
        setLeaveLabel(payload.leave_label || "");
        setStartDate(payload.start_date || "");
        setEndDate(payload.end_date || "");
        setPortion(payload.portion || "FULL");
        setReasonText(payload.reason_text || "");
      } catch (error) {
        toast.error(error instanceof Error ? error.message : "Could not load leave request");
      } finally {
        setLoadingExisting(false);
      }
    }
    void loadExisting();
  }, [editId]);

  const totalUploadBytes = useMemo(() => files.reduce((sum, file) => sum + file.size, 0), [files]);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (totalUploadBytes > MAX_TOTAL_DOC_BYTES) {
      toast.error("Supporting documents exceed 10 GB total size.");
      return;
    }

    setSubmitting(true);
    try {
      const payload = new FormData();
      payload.append("leave_type", leaveType);
      payload.append("leave_label", leaveLabel);
      payload.append("start_date", startDate);
      payload.append("end_date", endDate);
      payload.append("portion", portion);
      payload.append("reason_text", reasonText);
      for (const file of files) payload.append("documents", file);

      const response = await apiFetch(editId ? `/leave/requests/${editId}/` : "/leave/requests/", {
        method: editId ? "PATCH" : "POST",
        body: payload,
        headers: {},
      });
      const body = await response.json();
      if (!response.ok) {
        const detail = body?.detail || body?.errors?.non_field_errors?.join(" ") || "Leave request failed";
        throw new Error(detail);
      }
      toast.success(editId ? "Leave request updated" : body.message || "Leave request submitted");
      router.replace("/dashboard");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not submit leave request");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AppShell>
      <PageHeader
        title={editId ? "Edit Leave Request" : "Apply Leave"}
        description="Plan your time off with policy-aware validation, holiday exclusions, and approval workflow."
        badge={<Badge variant="outline">{editId ? "Edit Mode" : "New Request"}</Badge>}
      />

      <Card className="surface-card max-w-4xl">
        <CardHeader>
          <CardTitle>{editId ? "Update Request Details" : "Request Leave"}</CardTitle>
          <CardDescription>
            Weekends and configured holidays are excluded from working-day calculations.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {loadingExisting ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading request details...
            </div>
          ) : null}
          <form className="grid gap-5" onSubmit={onSubmit}>
            <div className="soft-panel grid gap-2">
              <Label htmlFor="leave-type">Leave Type</Label>
              <Select value={leaveType} onValueChange={setLeaveType} disabled={loadingTypes}>
                <SelectTrigger id="leave-type">
                  <SelectValue placeholder={loadingTypes ? "Loading..." : "Select leave type"} />
                </SelectTrigger>
                <SelectContent>
                  {leaveTypes.map((type) => (
                    <SelectItem value={String(type.id)} key={type.id}>
                      {type.name} (max {type.max_days})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="soft-panel grid gap-2">
              <Label htmlFor="leave-label">Label</Label>
              <Input
                id="leave-label"
                value={leaveLabel}
                onChange={(event) => setLeaveLabel(event.target.value)}
                placeholder="Short title"
                required
              />
            </div>

            <div className="soft-panel grid gap-4 md:grid-cols-2">
              <div className="grid gap-2">
                <Label htmlFor="start-date">Start Date</Label>
                <Input
                  id="start-date"
                  type="date"
                  value={startDate}
                  onChange={(event) => setStartDate(event.target.value)}
                  required
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="end-date">End Date</Label>
                <Input
                  id="end-date"
                  type="date"
                  value={endDate}
                  onChange={(event) => setEndDate(event.target.value)}
                  required
                />
              </div>
            </div>

            <div className="soft-panel grid gap-2">
              <Label htmlFor="portion">Portion</Label>
              <Select value={portion} onValueChange={setPortion}>
                <SelectTrigger id="portion">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="FULL">Full day</SelectItem>
                  <SelectItem value="HALF">Half day</SelectItem>
                  <SelectItem value="QUARTER">Quarter day</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="soft-panel grid gap-2">
              <Label htmlFor="reason">Reason</Label>
              <Textarea
                id="reason"
                value={reasonText}
                onChange={(event) => setReasonText(event.target.value)}
                placeholder="Reason for leave"
                required
              />
            </div>

            <div className="soft-panel grid gap-2">
              <Label htmlFor="docs">Supporting Documents (max total 10 GB)</Label>
              <Input
                id="docs"
                type="file"
                multiple
                onChange={(event) => setFiles(Array.from(event.target.files || []))}
              />
              <p className="text-xs text-muted-foreground">
                Selected {files.length} file(s), {(totalUploadBytes / (1024 * 1024)).toFixed(2)} MB
              </p>
            </div>

            <Button type="submit" disabled={submitting} className="w-full md:w-auto">
              {submitting ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  {editId ? "Saving..." : "Submitting..."}
                </>
              ) : (
                <>
                  <Send className="mr-2 h-4 w-4" />
                  {editId ? "Save Changes" : "Submit Leave Request"}
                </>
              )}
            </Button>
            <div className="soft-panel text-xs text-muted-foreground">
              <Paperclip className="mr-1 inline h-3.5 w-3.5" />
              Approval is required by admin/HR before leave is active.
            </div>
          </form>
        </CardContent>
      </Card>
    </AppShell>
  );
}

export default function ApplyLeavePage() {
  return (
    <Suspense
      fallback={
        <AppShell>
          <div className="page-wrap">
            <Card className="surface-card max-w-4xl">
              <CardContent className="flex items-center gap-2 py-8 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Loading leave form...
              </CardContent>
            </Card>
          </div>
        </AppShell>
      }
    >
      <ApplyLeavePageContent />
    </Suspense>
  );
}
