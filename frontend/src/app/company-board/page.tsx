"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { CalendarDays, Loader2, Search } from "lucide-react";
import { toast } from "sonner";

import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/page-header";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { apiFetch } from "@/lib/api";
import { getAccessToken, getAuthUser, isAdminOrHR } from "@/lib/auth";

type LeaveRow = {
  id: number;
  employee: number;
  employee_name: string;
  created_at: string;
  leave_type_name: string;
  leave_label: string;
  start_date: string;
  end_date: string;
  portion_label: string;
  requested_units: string;
  status: string;
  status_label: string;
  manager_note: string;
  display_reason: string;
};

type LeaveType = {
  id: number;
  name: string;
};

type UserOption = {
  id: number;
  full_name: string;
  username: string;
};

type Paginated<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};

function badgeVariant(status: string): "default" | "destructive" | "secondary" | "outline" {
  if (status === "APPROVED") return "default";
  if (status === "REJECTED") return "destructive";
  if (status === "PENDING") return "secondary";
  return "outline";
}

export default function CompanyBoardPage() {
  const router = useRouter();
  const user = getAuthUser();
  const [users, setUsers] = useState<UserOption[]>([]);
  const [leaveTypes, setLeaveTypes] = useState<LeaveType[]>([]);
  const [employeeFilter, setEmployeeFilter] = useState("");
  const [leaveTypeFilter, setLeaveTypeFilter] = useState("");
  const [monthFilter, setMonthFilter] = useState("");
  const [portionFilter, setPortionFilter] = useState("");
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [items, setItems] = useState<LeaveRow[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [nextPage, setNextPage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const canManage = isAdminOrHR(user);

  const filterQuery = useMemo(() => {
    const params = new URLSearchParams();
    if (query.trim()) params.set("q", query.trim());
    if (employeeFilter) params.set("employee", employeeFilter);
    if (leaveTypeFilter) params.set("leave_type", leaveTypeFilter);
    if (monthFilter) params.set("month", monthFilter);
    if (portionFilter) params.set("portion", portionFilter);
    if (statusFilter) params.set("status", statusFilter);
    return params.toString();
  }, [query, employeeFilter, leaveTypeFilter, monthFilter, portionFilter, statusFilter]);

  async function fetchPage(urlPath: string, append = false) {
    setLoading(true);
    try {
      const response = await apiFetch(urlPath);
      if (!response.ok) throw new Error("Failed to load leave board");
      const payload = (await response.json()) as Paginated<LeaveRow>;
      setItems((prev) => (append ? [...prev, ...payload.results] : payload.results));
      setTotalCount(payload.count);
      setNextPage(payload.next);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to load leave board");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    const path = `/leave/requests/${filterQuery ? `?${filterQuery}` : ""}`;
    void fetchPage(path, false);
  }, [router, filterQuery]);

  useEffect(() => {
    if (!getAccessToken()) return;
    async function loadLookups() {
      try {
        const typesResponse = await apiFetch("/leave/types/");
        if (typesResponse.ok) {
          const payload = (await typesResponse.json()) as LeaveType[];
          setLeaveTypes(payload);
        }
        if (canManage) {
          const usersResponse = await apiFetch("/admin/users/");
          if (usersResponse.ok) {
            const payload = (await usersResponse.json()) as UserOption[];
            setUsers(payload);
          }
        }
      } catch {
        // Non-blocking for board page.
      }
    }
    void loadLookups();
  }, [canManage]);

  function extractApiPath(nextUrl: string | null) {
    if (!nextUrl) return "";
    try {
      const parsed = new URL(nextUrl);
      return `${parsed.pathname.replace("/api", "")}${parsed.search}`;
    } catch {
      return "";
    }
  }

  return (
    <AppShell>
      <PageHeader
        title="Company Leave Board"
        description="Search, filter, and inspect leave activity with expandable details."
        badge={<Badge variant="outline">Board</Badge>}
      />

      <Card className="surface-card">
        <CardHeader>
          <CardTitle>Filter & Explore</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="soft-panel grid gap-3 md:grid-cols-6">
            <div className="relative md:col-span-2">
              <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
              <Input
                className="pl-9"
                placeholder="Search by name/email/reason..."
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
            </div>
            {canManage ? (
              <Select value={employeeFilter || "__ALL__"} onValueChange={(value) => setEmployeeFilter(value === "__ALL__" ? "" : value)}>
                <SelectTrigger>
                  <SelectValue placeholder="All employees" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__ALL__">All employees</SelectItem>
                  {users.map((user) => (
                    <SelectItem value={String(user.id)} key={user.id}>
                      {user.full_name || user.username}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : null}
            <Select value={leaveTypeFilter || "__ALL__"} onValueChange={(value) => setLeaveTypeFilter(value === "__ALL__" ? "" : value)}>
              <SelectTrigger>
                <SelectValue placeholder="All leave types" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__ALL__">All leave types</SelectItem>
                {leaveTypes.map((type) => (
                  <SelectItem value={String(type.id)} key={type.id}>
                    {type.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Input type="month" value={monthFilter} onChange={(event) => setMonthFilter(event.target.value)} />
            <Select value={portionFilter || "__ALL__"} onValueChange={(value) => setPortionFilter(value === "__ALL__" ? "" : value)}>
              <SelectTrigger>
                <SelectValue placeholder="All portions" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__ALL__">All portions</SelectItem>
                <SelectItem value="FULL">Full day</SelectItem>
                <SelectItem value="HALF">Half day</SelectItem>
                <SelectItem value="QUARTER">Quarter day</SelectItem>
              </SelectContent>
            </Select>
            <Select value={statusFilter || "__ALL__"} onValueChange={(value) => setStatusFilter(value === "__ALL__" ? "" : value)}>
              <SelectTrigger>
                <SelectValue placeholder="All statuses" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__ALL__">All statuses</SelectItem>
                <SelectItem value="PENDING">Pending</SelectItem>
                <SelectItem value="APPROVED">Approved</SelectItem>
                <SelectItem value="REJECTED">Rejected</SelectItem>
                <SelectItem value="CANCELLED">Cancelled</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border/60 bg-card/50 px-3 py-2">
            <p className="text-sm text-muted-foreground">{totalCount} leave request(s) found</p>
            {canManage ? (
              <Button
                variant="outline"
                className="bg-card/70"
                onClick={async () => {
                  const endpoint = `/leave/export.csv${filterQuery ? `?${filterQuery}` : ""}`;
                  const response = await apiFetch(endpoint, {
                    headers: { Accept: "text/csv" },
                  });
                  if (!response.ok) {
                    toast.error("Failed to export CSV");
                    return;
                  }
                  const csvText = await response.text();
                  const blob = new Blob([csvText], { type: "text/csv;charset=utf-8" });
                  const url = URL.createObjectURL(blob);
                  const link = document.createElement("a");
                  link.href = url;
                  link.download = "leave-board.csv";
                  link.click();
                  URL.revokeObjectURL(url);
                }}
              >
                Export CSV
              </Button>
            ) : null}
          </div>

          <div className="rounded-xl border border-border/60 bg-card/55 p-2">
            <Accordion type="multiple" className="w-full">
              {items.map((item) => (
                <AccordionItem value={String(item.id)} key={item.id}>
                  <AccordionTrigger className="px-2">
                    <div className="grid w-full gap-1 text-left md:grid-cols-5 md:items-center">
                      <span className="font-medium">{item.employee_name}</span>
                      <span className="text-sm text-muted-foreground">{item.leave_type_name}</span>
                      <span className="text-sm text-muted-foreground">{item.start_date} to {item.end_date}</span>
                      <span className="text-sm">{item.requested_units} unit(s)</span>
                      <span>
                        <Badge variant={badgeVariant(item.status)}>{item.status_label}</Badge>
                      </span>
                    </div>
                  </AccordionTrigger>
                  <AccordionContent className="space-y-3 px-2 pb-4">
                    <div className="grid gap-3 md:grid-cols-3">
                      <div>
                        <Label>Label</Label>
                        <p className="text-sm text-muted-foreground">{item.leave_label || "-"}</p>
                      </div>
                      <div>
                        <Label>Portion</Label>
                        <p className="text-sm text-muted-foreground">{item.portion_label}</p>
                      </div>
                      <div>
                        <Label>Created</Label>
                        <p className="text-sm text-muted-foreground">{new Date(item.created_at).toLocaleString()}</p>
                      </div>
                    </div>
                    <div>
                      <Label>Reason</Label>
                      <p className="text-sm text-muted-foreground">{item.display_reason || "-"}</p>
                    </div>
                    {item.manager_note ? (
                      <div>
                        <Label>Reviewer Note</Label>
                        <p className="text-sm text-muted-foreground">{item.manager_note}</p>
                      </div>
                    ) : null}
                  </AccordionContent>
                </AccordionItem>
              ))}
            </Accordion>
            {!items.length ? (
              <div className="soft-panel m-3 text-sm text-muted-foreground">
                {loading ? "Loading..." : "No leave requests found for the selected filters."}
              </div>
            ) : null}
          </div>

          <div className="soft-panel text-sm text-muted-foreground">
            <p className="inline-flex items-center gap-2 font-medium text-foreground">
              <CalendarDays className="h-4 w-4 text-primary" />
              Expand any entry to view reason, portion, and timestamp.
            </p>
          </div>

          {nextPage ? (
            <Button
              variant="outline"
              className="bg-card/70"
              disabled={loading}
              onClick={() => {
                const path = extractApiPath(nextPage);
                if (!path) return;
                void fetchPage(path, true);
              }}
            >
              {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              Load More
            </Button>
          ) : null}
        </CardContent>
      </Card>
    </AppShell>
  );
}
