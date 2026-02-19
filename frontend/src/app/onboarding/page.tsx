"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch } from "@/lib/api";
import { getAccessToken } from "@/lib/auth";

type Candidate = {
  id: number;
  full_name: string;
  org_unit: number | null;
  location: number | null;
};

type UserOption = {
  id: number;
  full_name: string;
  username: string;
};

type OnboardingTask = {
  id: number;
  candidate: number;
  candidate_name: string;
  title: string;
  description: string;
  due_date: string | null;
  owner: number | null;
  owner_name: string;
  status: string;
  status_label: string;
  category: string;
  category_label: string;
};

type FormFieldDef = {
  id: number;
  key: string;
  label: string;
  field_type: string;
  required: boolean;
  options: string[];
  placeholder: string;
  help_text: string;
};

const statusOptions = [
  { value: "PENDING", label: "TODO" },
  { value: "IN_PROGRESS", label: "IN_PROGRESS" },
  { value: "DONE", label: "DONE" },
  { value: "BLOCKED", label: "BLOCKED" },
] as const;

const categoryOptions = [
  { value: "GENERAL", label: "General" },
  { value: "HR", label: "HR" },
  { value: "IT", label: "IT" },
  { value: "FACILITIES", label: "Facilities" },
] as const;

function statusLabel(status: string) {
  const matched = statusOptions.find((option) => option.value === status);
  return matched?.label || status;
}

export default function OnboardingPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [tasks, setTasks] = useState<OnboardingTask[]>([]);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [users, setUsers] = useState<UserOption[]>([]);
  const [dynamicFields, setDynamicFields] = useState<FormFieldDef[]>([]);
  const [dynamicValues, setDynamicValues] = useState<Record<string, string>>({});
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [categoryFilter, setCategoryFilter] = useState("ALL");
  const [form, setForm] = useState({
    title: "",
    due_date: "",
    status: "PENDING",
    category: "GENERAL",
    candidate: "none",
    owner: "none",
    description: "",
  });

  const filteredTasks = useMemo(() => {
    return tasks.filter((task) => {
      const statusMatch = statusFilter === "ALL" || task.status === statusFilter;
      const categoryMatch = categoryFilter === "ALL" || task.category === categoryFilter;
      return statusMatch && categoryMatch;
    });
  }, [tasks, statusFilter, categoryFilter]);

  async function loadData() {
    setLoading(true);
    try {
      const [candidateResponse, userResponse, taskResponse] = await Promise.all([
        apiFetch("/talent/candidates/"),
        apiFetch("/admin/users/"),
        apiFetch("/onboarding/tasks/"),
      ]);

      if (!candidateResponse.ok || !taskResponse.ok || !userResponse.ok) {
        throw new Error("Failed to load onboarding data");
      }

      const candidatePayload = (await candidateResponse.json()) as Candidate[];
      const userPayload = (await userResponse.json()) as UserOption[];
      const taskPayload = (await taskResponse.json()) as OnboardingTask[];

      setCandidates(candidatePayload);
      setUsers(userPayload);
      setTasks(taskPayload);

      if (candidatePayload.length && form.candidate === "none") {
        setForm((prev) => ({ ...prev, candidate: String(candidatePayload[0].id) }));
      }
      const selectedCandidateId = form.candidate !== "none"
        ? form.candidate
        : (candidatePayload[0] ? String(candidatePayload[0].id) : "none");
      await loadDynamicFieldsForCandidate(selectedCandidateId, candidatePayload);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to load onboarding data");
    } finally {
      setLoading(false);
    }
  }

  async function loadDynamicFieldsForCandidate(candidateId: string, candidateList: Candidate[] = candidates) {
    if (!candidateId || candidateId === "none") {
      setDynamicFields([]);
      setDynamicValues({});
      return;
    }
    const selected = candidateList.find((candidate) => String(candidate.id) === candidateId);
    if (!selected) {
      setDynamicFields([]);
      setDynamicValues({});
      return;
    }
    const params = new URLSearchParams();
    params.set("module", "ONBOARDING");
    if (selected.org_unit) params.set("org_unit", String(selected.org_unit));
    if (selected.location) params.set("location", String(selected.location));
    const response = await apiFetch(`/org/form-fields/?${params.toString()}`);
    if (!response.ok) {
      throw new Error("Failed to load dynamic onboarding fields");
    }
    const payload = (await response.json()) as FormFieldDef[];
    setDynamicFields(payload);
    setDynamicValues((previous) => {
      const next: Record<string, string> = {};
      payload.forEach((field) => {
        next[field.key] = previous[field.key] ?? "";
      });
      return next;
    });
  }

  async function createTask() {
    if (!form.title.trim()) {
      toast.error("Title is required.");
      return;
    }
    if (form.candidate === "none") {
      toast.error("Select a candidate.");
      return;
    }
    for (const field of dynamicFields) {
      if (field.required && !String(dynamicValues[field.key] || "").trim()) {
        toast.error(`${field.label} is required.`);
        return;
      }
    }

    setSaving(true);
    try {
      const response = await apiFetch("/onboarding/tasks/", {
        method: "POST",
        body: JSON.stringify({
          title: form.title.trim(),
          candidate: Number(form.candidate),
          due_date: form.due_date || "",
          status: form.status,
          category: form.category,
          owner: form.owner === "none" ? null : Number(form.owner),
          description: form.description.trim(),
          custom_fields: dynamicValues,
        }),
      });

      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || "Could not create onboarding task");
      }

      toast.success("Onboarding task created");
      setForm((prev) => ({ ...prev, title: "", due_date: "", description: "", category: "GENERAL" }));
      setDynamicValues((previous) => {
        const reset: Record<string, string> = {};
        dynamicFields.forEach((field) => {
          reset[field.key] = previous[field.key] ? "" : "";
        });
        return reset;
      });
      await loadData();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not create onboarding task");
    } finally {
      setSaving(false);
    }
  }

  async function updateTaskStatus(taskId: number, status: string) {
    try {
      const response = await apiFetch(`/onboarding/tasks/${taskId}/`, {
        method: "PATCH",
        body: JSON.stringify({ status }),
      });
      if (!response.ok) {
        const payload = await response.json();
        throw new Error(payload.detail || "Could not update task status");
      }
      setTasks((prev) => prev.map((item) => (item.id === taskId ? { ...item, status, status_label: statusLabel(status) } : item)));
      toast.success("Task status updated");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not update task status");
    }
  }

  async function deleteTask(taskId: number) {
    try {
      const response = await apiFetch(`/onboarding/tasks/${taskId}/`, { method: "DELETE" });
      if (!response.ok && response.status !== 204) {
        throw new Error("Could not delete task");
      }
      setTasks((prev) => prev.filter((item) => item.id !== taskId));
      toast.success("Task deleted");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not delete task");
    }
  }

  useEffect(() => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    void loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router]);

  useEffect(() => {
    if (!getAccessToken()) return;
    loadDynamicFieldsForCandidate(form.candidate).catch((error) => {
      toast.error(error instanceof Error ? error.message : "Failed to load dynamic fields");
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form.candidate]);

  return (
    <AppShell>
      <PageHeader
        title="Onboarding"
        description="Create and monitor onboarding tasks for new hires."
        badge={<Badge variant="outline">HR / Admin</Badge>}
      />

      <Card className="surface-card">
        <CardHeader>
          <CardTitle>Create Onboarding Task</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
            <div className="xl:col-span-2">
              <Label htmlFor="task-title" className="mb-1 block">Title</Label>
              <Input
                id="task-title"
                placeholder="Create IT account"
                value={form.title}
                onChange={(event) => setForm((prev) => ({ ...prev, title: event.target.value }))}
              />
            </div>
            <div>
              <Label htmlFor="task-due" className="mb-1 block">Due Date</Label>
              <Input
                id="task-due"
                type="date"
                value={form.due_date}
                onChange={(event) => setForm((prev) => ({ ...prev, due_date: event.target.value }))}
              />
            </div>
            <div>
              <Label className="mb-1 block">Status</Label>
              <Select value={form.status} onValueChange={(value) => setForm((prev) => ({ ...prev, status: value }))}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {statusOptions.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="mb-1 block">Category</Label>
              <Select value={form.category} onValueChange={(value) => setForm((prev) => ({ ...prev, category: value }))}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {categoryOptions.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="mb-1 block">Candidate</Label>
              <Select value={form.candidate} onValueChange={(value) => setForm((prev) => ({ ...prev, candidate: value }))}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">None</SelectItem>
                  {candidates.map((candidate) => (
                    <SelectItem key={candidate.id} value={String(candidate.id)}>
                      {candidate.full_name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
            <div>
              <Label className="mb-1 block">Assigned To</Label>
              <Select value={form.owner} onValueChange={(value) => setForm((prev) => ({ ...prev, owner: value }))}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">Unassigned</SelectItem>
                  {users.map((user) => (
                    <SelectItem key={user.id} value={String(user.id)}>
                      {user.full_name || user.username}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="md:col-span-2 xl:col-span-3">
              <Label htmlFor="task-desc" className="mb-1 block">Description</Label>
              <Textarea
                id="task-desc"
                placeholder="Detailed onboarding notes"
                value={form.description}
                onChange={(event) => setForm((prev) => ({ ...prev, description: event.target.value }))}
              />
            </div>
            <div className="flex items-end">
              <Button className="w-full" onClick={createTask} disabled={saving}>
                {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Plus className="mr-2 h-4 w-4" />}
                Create
              </Button>
            </div>
          </div>

          {dynamicFields.length ? (
            <div className="space-y-2">
              <Label>Custom Fields</Label>
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {dynamicFields.map((field) => {
                  const currentValue = dynamicValues[field.key] ?? "";
                  const inputType =
                    field.field_type === "NUMBER"
                      ? "number"
                      : field.field_type === "DATE"
                        ? "date"
                        : field.field_type === "EMAIL"
                          ? "email"
                          : field.field_type === "PHONE"
                            ? "tel"
                            : field.field_type === "URL"
                              ? "url"
                              : "text";
                  return (
                    <div key={field.id} className="space-y-1">
                      <Label>{field.label}{field.required ? " *" : ""}</Label>
                      {field.field_type === "TEXTAREA" ? (
                        <Textarea
                          placeholder={field.placeholder || field.label}
                          value={currentValue}
                          onChange={(event) =>
                            setDynamicValues((prev) => ({ ...prev, [field.key]: event.target.value }))
                          }
                        />
                      ) : field.field_type === "SELECT" ? (
                        <Select
                          value={currentValue || "none"}
                          onValueChange={(value) =>
                            setDynamicValues((prev) => ({ ...prev, [field.key]: value === "none" ? "" : value }))
                          }
                        >
                          <SelectTrigger>
                            <SelectValue placeholder={field.placeholder || field.label} />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="none">Select</SelectItem>
                            {(field.options || []).map((option) => (
                              <SelectItem key={`${field.id}-${option}`} value={option}>
                                {option}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      ) : field.field_type === "CHECKBOX" ? (
                        <Select
                          value={currentValue || "false"}
                          onValueChange={(value) => setDynamicValues((prev) => ({ ...prev, [field.key]: value }))}
                        >
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="true">Yes</SelectItem>
                            <SelectItem value="false">No</SelectItem>
                          </SelectContent>
                        </Select>
                      ) : (
                        <Input
                          type={inputType}
                          placeholder={field.placeholder || field.label}
                          value={currentValue}
                          onChange={(event) =>
                            setDynamicValues((prev) => ({ ...prev, [field.key]: event.target.value }))
                          }
                        />
                      )}
                      {field.help_text ? <p className="text-xs text-muted-foreground">{field.help_text}</p> : null}
                    </div>
                  );
                })}
              </div>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card className="surface-card">
        <CardHeader className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <CardTitle>Onboarding Tracker</CardTitle>
          <div className="flex w-full flex-col gap-2 md:w-auto md:flex-row">
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="md:w-[160px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="ALL">All statuses</SelectItem>
                {statusOptions.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={categoryFilter} onValueChange={setCategoryFilter}>
              <SelectTrigger className="md:w-[160px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="ALL">All categories</SelectItem>
                {categoryOptions.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center gap-2 text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading onboarding tasks...
            </div>
          ) : filteredTasks.length ? (
            <Table className="[&_th]:h-10 [&_th]:text-xs [&_th]:uppercase [&_th]:tracking-wide">
              <TableHeader>
                <TableRow>
                  <TableHead>Task</TableHead>
                  <TableHead>Candidate</TableHead>
                  <TableHead>Category</TableHead>
                  <TableHead>Assigned To</TableHead>
                  <TableHead>Due Date</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredTasks.map((task) => (
                  <TableRow key={task.id}>
                    <TableCell>{task.title}</TableCell>
                    <TableCell>{task.candidate_name}</TableCell>
                    <TableCell>{task.category_label || task.category}</TableCell>
                    <TableCell>{task.owner_name || "Unassigned"}</TableCell>
                    <TableCell>{task.due_date || "-"}</TableCell>
                    <TableCell>
                      <Select value={task.status} onValueChange={(value) => void updateTaskStatus(task.id, value)}>
                        <SelectTrigger className="h-8 w-[160px]">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {statusOptions.map((option) => (
                            <SelectItem key={option.value} value={option.value}>
                              {option.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </TableCell>
                    <TableCell className="text-right">
                      <Button variant="ghost" size="icon" onClick={() => void deleteTask(task.id)}>
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <p className="text-sm text-muted-foreground">No onboarding tasks found.</p>
          )}
        </CardContent>
      </Card>
    </AppShell>
  );
}
