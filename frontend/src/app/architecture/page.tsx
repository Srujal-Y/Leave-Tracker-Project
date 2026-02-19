"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, Plus, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { apiFetch, readJsonSafely } from "@/lib/api";
import { getAccessToken, getAuthUser, isAdmin, isAdminOrHR } from "@/lib/auth";

type Thread = { id: number; module: string; title: string; created_by: number; created_at: string };
type Comment = { id: number; thread: number; author: number; body: string; created_at: string };
type Role = { id: number; code: string; name: string };
type Permission = { id: number; code: string; name: string };
type Audit = { id: number; event_type: string; entity_type: string; entity_id: string; created_at: string };
type WorkflowRule = { id: number; module: string; trigger_event: string; active: boolean };
type Job = { id: number; job_type: string; status: string; created_at: string };
type TenantConnection = { id: number; db_host: string; db_name: string; db_user: string; region: string; active: boolean };
type TenantJob = { id: number; job_type: string; status: string; created_at: string };

type Tab = "workspace" | "compliance" | "workflow" | "control";

function asList<T>(payload: unknown): T[] {
  if (Array.isArray(payload)) return payload as T[];
  if (payload && typeof payload === "object" && Array.isArray((payload as { results?: unknown[] }).results)) {
    return (payload as { results: T[] }).results;
  }
  return [];
}

function fmt(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

async function detail(response: Response, fallback: string) {
  const payload = await readJsonSafely<{ detail?: string; non_field_errors?: string[] }>(response);
  return payload?.detail || payload?.non_field_errors?.join(", ") || fallback;
}

export default function ArchitecturePage() {
  const router = useRouter();
  const user = getAuthUser();
  const canOpen = isAdminOrHR(user);
  const admin = isAdmin(user);

  const [tab, setTab] = useState<Tab>("workspace");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const [threads, setThreads] = useState<Thread[]>([]);
  const [comments, setComments] = useState<Comment[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [permissions, setPermissions] = useState<Permission[]>([]);
  const [audits, setAudits] = useState<Audit[]>([]);
  const [workflowRules, setWorkflowRules] = useState<WorkflowRule[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [connections, setConnections] = useState<TenantConnection[]>([]);
  const [tenantJobs, setTenantJobs] = useState<TenantJob[]>([]);

  const [threadModule, setThreadModule] = useState("GENERAL");
  const [threadTitle, setThreadTitle] = useState("");
  const [roleCode, setRoleCode] = useState("");
  const [roleName, setRoleName] = useState("");
  const [permissionCode, setPermissionCode] = useState("");
  const [permissionName, setPermissionName] = useState("");
  const [ruleModule, setRuleModule] = useState("LEAVE");
  const [triggerEvent, setTriggerEvent] = useState("");
  const [jobType, setJobType] = useState("REMINDER");
  const [dbHost, setDbHost] = useState("");
  const [dbName, setDbName] = useState("");
  const [dbUser, setDbUser] = useState("");
  const [secretRef, setSecretRef] = useState("");
  const [provisionType, setProvisionType] = useState("MIGRATE");

  async function loadWorkspace() {
    const [a, b] = await Promise.all([
      apiFetch("/architecture/workspace/threads/"),
      apiFetch("/architecture/workspace/comments/"),
    ]);
    if (!a.ok || !b.ok) throw new Error("Could not load workspace module.");
    setThreads(asList<Thread>(await a.json()));
    setComments(asList<Comment>(await b.json()));
  }

  async function loadCompliance() {
    const auditRes = await apiFetch("/architecture/compliance/immutable-audit-events/");
    if (!auditRes.ok) throw new Error("Could not load compliance module.");
    setAudits(asList<Audit>(await auditRes.json()));
    if (!admin) return;

    const [roleRes, permissionRes] = await Promise.all([
      apiFetch("/architecture/compliance/roles/"),
      apiFetch("/architecture/compliance/permissions/"),
    ]);
    if (!roleRes.ok || !permissionRes.ok) throw new Error("Could not load role and permission data.");
    setRoles(asList<Role>(await roleRes.json()));
    setPermissions(asList<Permission>(await permissionRes.json()));
  }

  async function loadWorkflow() {
    const [a, b] = await Promise.all([
      apiFetch("/architecture/workflow/rules/"),
      apiFetch("/architecture/workflow/job-queue/"),
    ]);
    if (!a.ok || !b.ok) throw new Error("Could not load workflow module.");
    setWorkflowRules(asList<WorkflowRule>(await a.json()));
    setJobs(asList<Job>(await b.json()));
  }

  async function loadControl() {
    const [a, b] = await Promise.all([
      apiFetch("/architecture/control/tenant-connections/"),
      apiFetch("/architecture/control/tenant-provision-jobs/"),
    ]);
    if (!a.ok || !b.ok) throw new Error("Could not load control plane module.");
    setConnections(asList<TenantConnection>(await a.json()));
    setTenantJobs(asList<TenantJob>(await b.json()));
  }

  async function loadByTab(target: Tab) {
    if (target === "workspace") await loadWorkspace();
    if (target === "compliance") await loadCompliance();
    if (target === "workflow") await loadWorkflow();
    if (target === "control") await loadControl();
  }

  async function createThread() {
    if (!threadTitle.trim()) return toast.error("Thread title is required.");
    setSaving(true);
    try {
      const res = await apiFetch("/architecture/workspace/threads/", {
        method: "POST",
        body: JSON.stringify({ module: threadModule, title: threadTitle.trim() }),
      });
      if (!res.ok) throw new Error(await detail(res, "Could not create thread."));
      setThreadTitle("");
      await loadWorkspace();
      toast.success("Thread created.");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not create thread.");
    } finally {
      setSaving(false);
    }
  }

  async function createRole() {
    if (!admin) return;
    if (!roleCode.trim() || !roleName.trim()) return toast.error("Role code and name are required.");
    setSaving(true);
    try {
      const res = await apiFetch("/architecture/compliance/roles/", {
        method: "POST",
        body: JSON.stringify({ code: roleCode.trim().toUpperCase(), name: roleName.trim() }),
      });
      if (!res.ok) throw new Error(await detail(res, "Could not create role."));
      setRoleCode("");
      setRoleName("");
      await loadCompliance();
      toast.success("Role created.");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not create role.");
    } finally {
      setSaving(false);
    }
  }

  async function createPermission() {
    if (!admin) return;
    if (!permissionCode.trim() || !permissionName.trim()) return toast.error("Permission code and name are required.");
    setSaving(true);
    try {
      const res = await apiFetch("/architecture/compliance/permissions/", {
        method: "POST",
        body: JSON.stringify({ code: permissionCode.trim().toUpperCase(), name: permissionName.trim() }),
      });
      if (!res.ok) throw new Error(await detail(res, "Could not create permission."));
      setPermissionCode("");
      setPermissionName("");
      await loadCompliance();
      toast.success("Permission created.");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not create permission.");
    } finally {
      setSaving(false);
    }
  }

  async function createRule() {
    if (!triggerEvent.trim()) return toast.error("Trigger event is required.");
    setSaving(true);
    try {
      const res = await apiFetch("/architecture/workflow/rules/", {
        method: "POST",
        body: JSON.stringify({ module: ruleModule, trigger_event: triggerEvent.trim(), active: true }),
      });
      if (!res.ok) throw new Error(await detail(res, "Could not create workflow rule."));
      setTriggerEvent("");
      await loadWorkflow();
      toast.success("Workflow rule created.");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not create workflow rule.");
    } finally {
      setSaving(false);
    }
  }

  async function createJob() {
    if (!jobType.trim()) return toast.error("Job type is required.");
    setSaving(true);
    try {
      const res = await apiFetch("/architecture/workflow/job-queue/", {
        method: "POST",
        body: JSON.stringify({ job_type: jobType.trim(), payload_json: {}, status: "READY" }),
      });
      if (!res.ok) throw new Error(await detail(res, "Could not enqueue job."));
      await loadWorkflow();
      toast.success("Job queued.");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not enqueue job.");
    } finally {
      setSaving(false);
    }
  }

  async function createConnection() {
    if (!dbHost.trim() || !dbName.trim() || !dbUser.trim() || !secretRef.trim()) {
      return toast.error("Host, DB name, DB user, and secret reference are required.");
    }
    setSaving(true);
    try {
      const res = await apiFetch("/architecture/control/tenant-connections/", {
        method: "POST",
        body: JSON.stringify({
          db_host: dbHost.trim(),
          db_name: dbName.trim(),
          db_user: dbUser.trim(),
          secret_ref: secretRef.trim(),
          region: "",
          active: true,
        }),
      });
      if (!res.ok) throw new Error(await detail(res, "Could not create tenant connection."));
      await loadControl();
      toast.success("Tenant connection created.");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not create tenant connection.");
    } finally {
      setSaving(false);
    }
  }

  async function createProvisionJob() {
    setSaving(true);
    try {
      const res = await apiFetch("/architecture/control/tenant-provision-jobs/", {
        method: "POST",
        body: JSON.stringify({ job_type: provisionType, status: "PENDING" }),
      });
      if (!res.ok) throw new Error(await detail(res, "Could not create provision job."));
      await loadControl();
      toast.success("Provision job created.");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not create provision job.");
    } finally {
      setSaving(false);
    }
  }

  useEffect(() => {
    if (!getAccessToken()) return router.replace("/login");
    if (!canOpen) return router.replace("/dashboard");
    void (async () => {
      setLoading(true);
      try {
        await Promise.all([loadWorkspace(), loadCompliance(), loadWorkflow(), loadControl()]);
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "Could not load architecture modules.");
      } finally {
        setLoading(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router, canOpen, admin]);

  if (!canOpen) {
    return (
      <AppShell>
        <PageHeader title="Architecture" description="HR/Admin only." badge={<Badge variant="outline">Restricted</Badge>} />
      </AppShell>
    );
  }

  return (
    <AppShell>
      <PageHeader
        title="Architecture"
        description="These modules are now visible inside the main website."
        badge={<Badge variant="outline">Integrated</Badge>}
        actions={
          <Button variant="outline" onClick={() => void loadByTab(tab)} disabled={loading || saving}>
            {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}
            Refresh Tab
          </Button>
        }
      />

      <Tabs value={tab} onValueChange={(value) => setTab(value as Tab)} className="space-y-6">
        <TabsList className="grid w-full grid-cols-2 md:grid-cols-4">
          <TabsTrigger value="workspace">Workspace</TabsTrigger>
          <TabsTrigger value="compliance">Compliance</TabsTrigger>
          <TabsTrigger value="workflow">Workflow</TabsTrigger>
          <TabsTrigger value="control">Control Plane</TabsTrigger>
        </TabsList>

        <TabsContent value="workspace" className="space-y-6">
          <Card className="surface-card">
            <CardHeader><CardTitle>Add Workspace Thread</CardTitle></CardHeader>
            <CardContent className="grid gap-3 md:grid-cols-4">
              <Select value={threadModule} onValueChange={setThreadModule}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="GENERAL">GENERAL</SelectItem>
                  <SelectItem value="LEAVE">LEAVE</SelectItem>
                  <SelectItem value="TALENT">TALENT</SelectItem>
                  <SelectItem value="ONBOARDING">ONBOARDING</SelectItem>
                </SelectContent>
              </Select>
              <Input className="md:col-span-2" placeholder="Thread title" value={threadTitle} onChange={(e) => setThreadTitle(e.target.value)} />
              <Button onClick={() => void createThread()} disabled={saving}>{saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Plus className="mr-2 h-4 w-4" />}Add</Button>
            </CardContent>
          </Card>
          <Card className="surface-card">
            <CardHeader><CardTitle>Workspace Threads / Comments</CardTitle></CardHeader>
            <CardContent className="space-y-6">
              <Table><TableHeader><TableRow><TableHead>Title</TableHead><TableHead>Module</TableHead><TableHead>Created</TableHead></TableRow></TableHeader><TableBody>{threads.slice(0, 20).map((t) => (<TableRow key={t.id}><TableCell>{t.title}</TableCell><TableCell>{t.module}</TableCell><TableCell>{fmt(t.created_at)}</TableCell></TableRow>))}</TableBody></Table>
              <Table><TableHeader><TableRow><TableHead>Thread</TableHead><TableHead>Author</TableHead><TableHead>Body</TableHead></TableRow></TableHeader><TableBody>{comments.slice(0, 20).map((c) => (<TableRow key={c.id}><TableCell>{c.thread}</TableCell><TableCell>{c.author}</TableCell><TableCell className="max-w-[420px] truncate">{c.body}</TableCell></TableRow>))}</TableBody></Table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="compliance" className="space-y-6">
          {admin ? (
            <Card className="surface-card">
              <CardHeader><CardTitle>Add Role / Permission</CardTitle></CardHeader>
              <CardContent className="grid gap-3 md:grid-cols-3">
                <Input placeholder="Role code" value={roleCode} onChange={(e) => setRoleCode(e.target.value)} />
                <Input placeholder="Role name" value={roleName} onChange={(e) => setRoleName(e.target.value)} />
                <Button onClick={() => void createRole()} disabled={saving}>{saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Plus className="mr-2 h-4 w-4" />}Add Role</Button>
                <Input placeholder="Permission code" value={permissionCode} onChange={(e) => setPermissionCode(e.target.value)} />
                <Input placeholder="Permission name" value={permissionName} onChange={(e) => setPermissionName(e.target.value)} />
                <Button onClick={() => void createPermission()} disabled={saving}>{saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Plus className="mr-2 h-4 w-4" />}Add Permission</Button>
              </CardContent>
            </Card>
          ) : null}
          <Card className="surface-card">
            <CardHeader><CardTitle>Compliance Records</CardTitle></CardHeader>
            <CardContent className="space-y-6">
              {admin ? (
                <>
                  <Table><TableHeader><TableRow><TableHead>Role</TableHead><TableHead>Name</TableHead></TableRow></TableHeader><TableBody>{roles.map((r) => (<TableRow key={r.id}><TableCell>{r.code}</TableCell><TableCell>{r.name}</TableCell></TableRow>))}</TableBody></Table>
                  <Table><TableHeader><TableRow><TableHead>Permission</TableHead><TableHead>Name</TableHead></TableRow></TableHeader><TableBody>{permissions.map((p) => (<TableRow key={p.id}><TableCell>{p.code}</TableCell><TableCell>{p.name}</TableCell></TableRow>))}</TableBody></Table>
                </>
              ) : null}
              <Table><TableHeader><TableRow><TableHead>Event</TableHead><TableHead>Entity</TableHead><TableHead>Created</TableHead></TableRow></TableHeader><TableBody>{audits.slice(0, 20).map((a) => (<TableRow key={a.id}><TableCell>{a.event_type}</TableCell><TableCell>{a.entity_type}:{a.entity_id || "-"}</TableCell><TableCell>{fmt(a.created_at)}</TableCell></TableRow>))}</TableBody></Table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="workflow" className="space-y-6">
          <Card className="surface-card">
            <CardHeader><CardTitle>Add Workflow Rule / Job</CardTitle></CardHeader>
            <CardContent className="grid gap-3 md:grid-cols-3">
              <Select value={ruleModule} onValueChange={setRuleModule}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="LEAVE">LEAVE</SelectItem><SelectItem value="TALENT">TALENT</SelectItem><SelectItem value="ONBOARDING">ONBOARDING</SelectItem></SelectContent></Select>
              <Input placeholder="Trigger event" value={triggerEvent} onChange={(e) => setTriggerEvent(e.target.value)} />
              <Button onClick={() => void createRule()} disabled={saving}>{saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Plus className="mr-2 h-4 w-4" />}Add Rule</Button>
              <Input placeholder="Job type" value={jobType} onChange={(e) => setJobType(e.target.value)} />
              <div />
              <Button onClick={() => void createJob()} disabled={saving}>{saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Plus className="mr-2 h-4 w-4" />}Queue Job</Button>
            </CardContent>
          </Card>
          <Card className="surface-card">
            <CardHeader><CardTitle>Workflow Records</CardTitle></CardHeader>
            <CardContent className="space-y-6">
              <Table><TableHeader><TableRow><TableHead>Module</TableHead><TableHead>Trigger</TableHead><TableHead>Active</TableHead></TableRow></TableHeader><TableBody>{workflowRules.map((r) => (<TableRow key={r.id}><TableCell>{r.module}</TableCell><TableCell>{r.trigger_event}</TableCell><TableCell>{r.active ? "Yes" : "No"}</TableCell></TableRow>))}</TableBody></Table>
              <Table><TableHeader><TableRow><TableHead>Job Type</TableHead><TableHead>Status</TableHead><TableHead>Created</TableHead></TableRow></TableHeader><TableBody>{jobs.slice(0, 20).map((j) => (<TableRow key={j.id}><TableCell>{j.job_type}</TableCell><TableCell>{j.status}</TableCell><TableCell>{fmt(j.created_at)}</TableCell></TableRow>))}</TableBody></Table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="control" className="space-y-6">
          <Card className="surface-card">
            <CardHeader><CardTitle>Add Tenant Connection / Job</CardTitle></CardHeader>
            <CardContent className="grid gap-3 md:grid-cols-3">
              <Input placeholder="DB host" value={dbHost} onChange={(e) => setDbHost(e.target.value)} />
              <Input placeholder="DB name" value={dbName} onChange={(e) => setDbName(e.target.value)} />
              <Input placeholder="DB user" value={dbUser} onChange={(e) => setDbUser(e.target.value)} />
              <Input placeholder="Secret ref" value={secretRef} onChange={(e) => setSecretRef(e.target.value)} />
              <Select value={provisionType} onValueChange={setProvisionType}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="CREATE_DB">CREATE_DB</SelectItem>
                  <SelectItem value="MIGRATE">MIGRATE</SelectItem>
                  <SelectItem value="BACKUP">BACKUP</SelectItem>
                  <SelectItem value="RESTORE">RESTORE</SelectItem>
                </SelectContent>
              </Select>
              <div className="grid gap-2 md:grid-cols-2">
                <Button onClick={() => void createConnection()} disabled={saving}>{saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Plus className="mr-2 h-4 w-4" />}Save Connection</Button>
                <Button onClick={() => void createProvisionJob()} disabled={saving}>{saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Plus className="mr-2 h-4 w-4" />}Add Job</Button>
              </div>
            </CardContent>
          </Card>
          <Card className="surface-card">
            <CardHeader><CardTitle>Tenant Control Records</CardTitle></CardHeader>
            <CardContent className="space-y-6">
              <Table><TableHeader><TableRow><TableHead>Host</TableHead><TableHead>DB</TableHead><TableHead>User</TableHead><TableHead>Region</TableHead></TableRow></TableHeader><TableBody>{connections.map((c) => (<TableRow key={c.id}><TableCell>{c.db_host}</TableCell><TableCell>{c.db_name}</TableCell><TableCell>{c.db_user}</TableCell><TableCell>{c.region || "-"}</TableCell></TableRow>))}</TableBody></Table>
              <Table><TableHeader><TableRow><TableHead>Type</TableHead><TableHead>Status</TableHead><TableHead>Created</TableHead></TableRow></TableHeader><TableBody>{tenantJobs.slice(0, 20).map((j) => (<TableRow key={j.id}><TableCell>{j.job_type}</TableCell><TableCell>{j.status}</TableCell><TableCell>{fmt(j.created_at)}</TableCell></TableRow>))}</TableBody></Table>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </AppShell>
  );
}

