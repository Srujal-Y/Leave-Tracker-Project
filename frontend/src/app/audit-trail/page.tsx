"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiFetch } from "@/lib/api";
import { getAccessToken, getAuthUser, isAdminOrHR } from "@/lib/auth";

type AuditEvent = {
  id: number;
  actor_name: string;
  action: string;
  entity_type: string;
  entity_id: string;
  created_at: string;
};

type Paginated<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};

export default function AuditTrailPage() {
  const router = useRouter();
  const canManage = isAdminOrHR(getAuthUser());
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [nextPage, setNextPage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function load(path = "/audit/events/", append = false) {
    setLoading(true);
    try {
      const response = await apiFetch(path);
      if (!response.ok) throw new Error("Could not load audit events");
      const payload = (await response.json()) as Paginated<AuditEvent>;
      setEvents((prev) => (append ? [...prev, ...payload.results] : payload.results));
      setNextPage(payload.next);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not load audit events");
    } finally {
      setLoading(false);
    }
  }

  function extractApiPath(nextUrl: string | null) {
    if (!nextUrl) return "";
    try {
      const parsed = new URL(nextUrl);
      return `${parsed.pathname.replace("/api", "")}${parsed.search}`;
    } catch {
      return "";
    }
  }

  useEffect(() => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    void load();
  }, [router]);

  if (!canManage) {
    return (
      <AppShell>
        <PageHeader
          title="Audit Trail"
          description="Only HR/Admin can view audit logs."
          badge={<Badge variant="outline">Restricted</Badge>}
        />
        <Card className="surface-card">
          <CardHeader>
            <CardTitle>Audit Trail</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">Only HR/Admin can view audit logs.</p>
          </CardContent>
        </Card>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <PageHeader
        title="Audit Trail"
        description="Track create, edit, delete, and approval events with actor and timestamp."
        badge={<Badge variant="outline">Compliance</Badge>}
      />

      <Card className="surface-card">
        <CardHeader>
          <CardTitle>Audit Trail</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <Table className="[&_th]:h-11 [&_th]:text-xs [&_th]:uppercase [&_th]:tracking-wide">
            <TableHeader>
              <TableRow>
                <TableHead>When</TableHead>
                <TableHead>Actor</TableHead>
                <TableHead>Action</TableHead>
                <TableHead>Entity</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {events.length ? (
                events.map((event) => (
                  <TableRow key={event.id}>
                    <TableCell>{new Date(event.created_at).toLocaleString()}</TableCell>
                    <TableCell>{event.actor_name}</TableCell>
                    <TableCell>
                      <Badge variant="secondary">{event.action}</Badge>
                    </TableCell>
                    <TableCell>
                      {event.entity_type} #{event.entity_id}
                    </TableCell>
                  </TableRow>
                ))
              ) : (
                <TableRow>
                  <TableCell colSpan={4} className="text-muted-foreground">
                    {loading ? "Loading..." : "No audit logs found."}
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
          {nextPage ? (
            <Button
              variant="outline"
              disabled={loading}
              onClick={() => {
                const path = extractApiPath(nextPage);
                if (!path) return;
                void load(path, true);
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
