"use client";

import { useEffect, useMemo, useRef, useState } from "react";
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
import { getAccessToken, getAuthUser } from "@/lib/auth";

type Candidate = {
  id: number;
  full_name: string;
  email: string;
  company: number | null;
  company_slug: string;
  org_unit: number | null;
  org_unit_name: string;
  location: number | null;
  location_name: string;
  cost_center: number | null;
  cost_center_code: string;
  hiring_manager: number | null;
  hiring_manager_name: string;
  phone: string;
  role_applied: string;
  source: string;
  expected_join: string | null;
  resume_link: string;
  owner: number | null;
  owner_name: string;
  stage: string;
  stage_label: string;
  notes: string;
  task_count: number;
  created_at: string;
  updated_at: string;
};

type UserOption = {
  id: number;
  full_name: string;
  username: string;
};

type OrgUnitOption = {
  id: number;
  name: string;
};

type LocationOption = {
  id: number;
  name: string;
};

type CostCenterOption = {
  id: number;
  code: string;
  name: string;
};

type EmployeeOption = {
  id: number;
  user_name: string;
  position_title: string;
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

const stageOptions = [
  { value: "APPLIED", label: "APPLIED" },
  { value: "SCREENING", label: "SCREENING" },
  { value: "INTERVIEW", label: "INTERVIEW" },
  { value: "OFFER", label: "OFFER" },
  { value: "HIRED", label: "HIRED" },
  { value: "REJECTED", label: "REJECTED" },
] as const;

export default function TalentPage() {
  const router = useRouter();
  const authUser = getAuthUser();
  const [loading, setLoading] = useState(true);
  const [candidateLoading, setCandidateLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [owners, setOwners] = useState<UserOption[]>([]);
  const [orgUnits, setOrgUnits] = useState<OrgUnitOption[]>([]);
  const [locations, setLocations] = useState<LocationOption[]>([]);
  const [costCenters, setCostCenters] = useState<CostCenterOption[]>([]);
  const [employeeRecords, setEmployeeRecords] = useState<EmployeeOption[]>([]);
  const [dynamicFields, setDynamicFields] = useState<FormFieldDef[]>([]);
  const [dynamicValues, setDynamicValues] = useState<Record<string, string>>({});
  const [search, setSearch] = useState("");
  const [stageFilter, setStageFilter] = useState("ALL");
  const [orgUnitFilter, setOrgUnitFilter] = useState("ALL");
  const [locationFilter, setLocationFilter] = useState("ALL");
  const hasBootstrapped = useRef(false);
  const [form, setForm] = useState({
    full_name: "",
    email: "",
    org_unit: "none",
    location_name: "",
    cost_center: "none",
    hiring_manager: "none",
    phone: "",
    role_applied: "",
    source: "",
    stage: "APPLIED",
    expected_join: "",
    resume_link: "",
    owner: authUser?.id ? String(authUser.id) : "",
    notes: "",
  });

  const ownerLabelById = useMemo(() => {
    const labels = new Map<number, string>();
    owners.forEach((user) => labels.set(user.id, user.full_name || user.username));
    return labels;
  }, [owners]);

  async function loadCandidates(options?: { showLoader?: boolean }) {
    const showLoader = options?.showLoader ?? false;
    if (showLoader) {
      setCandidateLoading(true);
    }
    const params = new URLSearchParams();
    if (search.trim()) params.set("q", search.trim());
    if (stageFilter !== "ALL") params.set("stage", stageFilter);
    if (orgUnitFilter !== "ALL") params.set("org_unit", orgUnitFilter);
    if (locationFilter !== "ALL") params.set("location", locationFilter);

    try {
      const response = await apiFetch(`/talent/candidates/?${params.toString()}`);
      if (!response.ok) {
        throw new Error("Failed to load candidates");
      }
      const payload = (await response.json()) as Candidate[];
      setCandidates(payload);
    } finally {
      if (showLoader) {
        setCandidateLoading(false);
      }
    }
  }

  async function loadOwners() {
    const response = await apiFetch("/admin/users/");
    if (!response.ok) {
      throw new Error("Failed to load users");
    }
    const payload = (await response.json()) as UserOption[];
    setOwners(payload);
  }

  async function loadOrgData() {
    const [unitsResponse, locationsResponse, costCentersResponse, employeesResponse] = await Promise.all([
      apiFetch("/org/units/"),
      apiFetch("/org/locations/"),
      apiFetch("/org/cost-centers/"),
      apiFetch("/hr/employees/"),
    ]);
    if (!unitsResponse.ok || !locationsResponse.ok || !costCentersResponse.ok || !employeesResponse.ok) {
      throw new Error("Failed to load organization data");
    }
    const unitsPayload = (await unitsResponse.json()) as OrgUnitOption[];
    const locationsPayload = (await locationsResponse.json()) as LocationOption[];
    const costCentersPayload = (await costCentersResponse.json()) as CostCenterOption[];
    const employeesPayload = (await employeesResponse.json()) as EmployeeOption[];
    setOrgUnits(unitsPayload);
    setLocations(locationsPayload);
    setCostCenters(costCentersPayload);
    setEmployeeRecords(employeesPayload);
  }

  function findLocationByName(name: string) {
    const normalized = name.trim().toLowerCase();
    if (!normalized) return null;
    return locations.find((item) => item.name.trim().toLowerCase() === normalized) || null;
  }

  async function loadDynamicFields(orgUnit: string, locationName: string) {
    const params = new URLSearchParams();
    params.set("module", "TALENT");
    if (orgUnit !== "none") params.set("org_unit", orgUnit);
    const matchedLocation = findLocationByName(locationName);
    if (matchedLocation) params.set("location", String(matchedLocation.id));
    const response = await apiFetch(`/org/form-fields/?${params.toString()}`);
    if (!response.ok) {
      throw new Error("Failed to load dynamic talent form fields");
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

  async function loadBootstrapData() {
    setLoading(true);
    try {
      await Promise.all([loadOwners(), loadOrgData(), loadCandidates()]);
      await loadDynamicFields(form.org_unit, form.location_name);
      hasBootstrapped.current = true;
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to load talent data");
    } finally {
      setLoading(false);
    }
  }

  async function createCandidate() {
    if (!form.full_name.trim() || !form.email.trim() || !form.role_applied.trim()) {
      toast.error("Full name, email, and role title are required.");
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
      const response = await apiFetch("/talent/candidates/", {
        method: "POST",
        body: JSON.stringify({
          full_name: form.full_name.trim(),
          email: form.email.trim(),
          org_unit: form.org_unit === "none" ? null : Number(form.org_unit),
          location: findLocationByName(form.location_name)?.id ?? null,
          location_name: form.location_name.trim(),
          cost_center: form.cost_center === "none" ? null : Number(form.cost_center),
          hiring_manager: form.hiring_manager === "none" ? null : Number(form.hiring_manager),
          phone: form.phone.trim(),
          role_applied: form.role_applied.trim(),
          source: form.source.trim(),
          stage: form.stage,
          expected_join: form.expected_join || "",
          resume_link: form.resume_link.trim(),
          owner: form.owner || null,
          notes: form.notes.trim(),
          custom_fields: dynamicValues,
        }),
      });

      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || "Could not add candidate");
      }

      toast.success("Candidate added");
      setForm((prev) => ({
        ...prev,
        full_name: "",
        email: "",
        org_unit: "none",
        location_name: "",
        cost_center: "none",
        hiring_manager: "none",
        phone: "",
        role_applied: "",
        source: "",
        stage: "APPLIED",
        expected_join: "",
        resume_link: "",
        notes: "",
      }));
      setDynamicValues((previous) => {
        const reset: Record<string, string> = {};
        dynamicFields.forEach((field) => {
          reset[field.key] = previous[field.key] ? "" : "";
        });
        return reset;
      });
      await loadCandidates();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not add candidate");
    } finally {
      setSaving(false);
    }
  }

  async function updateCandidateStage(candidateId: number, stage: string) {
    try {
      const response = await apiFetch(`/talent/candidates/${candidateId}/`, {
        method: "PATCH",
        body: JSON.stringify({ stage }),
      });
      if (!response.ok) {
        const payload = await response.json();
        throw new Error(payload.detail || "Could not update stage");
      }
      setCandidates((prev) => prev.map((item) => (item.id === candidateId ? { ...item, stage, stage_label: stage } : item)));
      toast.success("Stage updated");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not update stage");
    }
  }

  async function deleteCandidate(candidateId: number) {
    try {
      const response = await apiFetch(`/talent/candidates/${candidateId}/`, { method: "DELETE" });
      if (!response.ok && response.status !== 204) {
        throw new Error("Could not delete candidate");
      }
      setCandidates((prev) => prev.filter((item) => item.id !== candidateId));
      toast.success("Candidate deleted");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not delete candidate");
    }
  }

  useEffect(() => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    void loadBootstrapData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router]);

  useEffect(() => {
    if (!getAccessToken()) return;
    if (!hasBootstrapped.current) return;
    loadCandidates({ showLoader: true }).catch((error) => {
      toast.error(error instanceof Error ? error.message : "Failed to load candidates");
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stageFilter, orgUnitFilter, locationFilter]);

  useEffect(() => {
    if (!getAccessToken()) return;
    loadDynamicFields(form.org_unit, form.location_name).catch((error) => {
      toast.error(error instanceof Error ? error.message : "Failed to load dynamic fields");
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form.org_unit, form.location_name]);

  return (
    <AppShell>
      <PageHeader
        title="Talent Acquisition"
        description="Track candidate pipeline, stage progression, and hiring notes."
        badge={<Badge variant="outline">HR / Admin</Badge>}
      />

      <Card className="surface-card">
        <CardHeader>
          <CardTitle>Add Candidate</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
            <Input
              placeholder="Full name"
              value={form.full_name}
              onChange={(event) => setForm((prev) => ({ ...prev, full_name: event.target.value }))}
            />
            <Input
              placeholder="Email"
              value={form.email}
              onChange={(event) => setForm((prev) => ({ ...prev, email: event.target.value }))}
            />
            <Input
              placeholder="Phone number"
              value={form.phone}
              onChange={(event) => setForm((prev) => ({ ...prev, phone: event.target.value }))}
            />
            <Input
              placeholder="Role title"
              value={form.role_applied}
              onChange={(event) => setForm((prev) => ({ ...prev, role_applied: event.target.value }))}
            />
            <Input
              placeholder="Source (LinkedIn, referral...)"
              value={form.source}
              onChange={(event) => setForm((prev) => ({ ...prev, source: event.target.value }))}
            />
          </div>

          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <div>
              <Label className="mb-1 block">Org Unit</Label>
              <Select value={form.org_unit} onValueChange={(value) => setForm((prev) => ({ ...prev, org_unit: value }))}>
                <SelectTrigger>
                  <SelectValue placeholder="Org unit" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">None</SelectItem>
                  {orgUnits.map((unit) => (
                    <SelectItem key={unit.id} value={String(unit.id)}>
                      {unit.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="mb-1 block">Location</Label>
              <Input
                placeholder="Type location manually"
                value={form.location_name}
                onChange={(event) => setForm((prev) => ({ ...prev, location_name: event.target.value }))}
              />
            </div>
            <div>
              <Label className="mb-1 block">Cost Center</Label>
              <Select value={form.cost_center} onValueChange={(value) => setForm((prev) => ({ ...prev, cost_center: value }))}>
                <SelectTrigger>
                  <SelectValue placeholder="Cost center" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">None</SelectItem>
                  {costCenters.map((item) => (
                    <SelectItem key={item.id} value={String(item.id)}>
                      {item.code} - {item.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="mb-1 block">Hiring Manager</Label>
              <Select value={form.hiring_manager} onValueChange={(value) => setForm((prev) => ({ ...prev, hiring_manager: value }))}>
                <SelectTrigger>
                  <SelectValue placeholder="Hiring manager" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">None</SelectItem>
                  {employeeRecords.map((record) => (
                    <SelectItem key={record.id} value={String(record.id)}>
                      {record.user_name || `Employee #${record.id}`}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-12">
            <div className="xl:col-span-2">
              <Select value={form.stage} onValueChange={(value) => setForm((prev) => ({ ...prev, stage: value }))}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {stageOptions.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Input
              type="date"
              className="xl:col-span-2"
              value={form.expected_join}
              onChange={(event) => setForm((prev) => ({ ...prev, expected_join: event.target.value }))}
            />
            <Input
              className="xl:col-span-4"
              placeholder="Resume link (optional)"
              value={form.resume_link}
              onChange={(event) => setForm((prev) => ({ ...prev, resume_link: event.target.value }))}
            />
            <div className="xl:col-span-2">
              <Select value={form.owner || "none"} onValueChange={(value) => setForm((prev) => ({ ...prev, owner: value === "none" ? "" : value }))}>
                <SelectTrigger>
                  <SelectValue placeholder="Owner" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">Unassigned</SelectItem>
                  {owners.map((owner) => (
                    <SelectItem key={owner.id} value={String(owner.id)}>
                      {owner.full_name || owner.username}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Button className="xl:col-span-2" onClick={createCandidate} disabled={saving}>
              {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Plus className="mr-2 h-4 w-4" />}
              Add
            </Button>
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

          <div className="space-y-1">
            <Label htmlFor="candidate-notes">Notes</Label>
            <Textarea
              id="candidate-notes"
              placeholder="Notes"
              value={form.notes}
              onChange={(event) => setForm((prev) => ({ ...prev, notes: event.target.value }))}
            />
          </div>
        </CardContent>
      </Card>

      <Card className="surface-card">
        <CardHeader className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <CardTitle>Candidate Pipeline</CardTitle>
          <div className="flex w-full flex-col gap-2 md:w-auto md:flex-row">
            <Input
              className="md:w-[220px]"
              placeholder="Search candidates"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  void loadCandidates();
                }
              }}
            />
            <Select value={stageFilter} onValueChange={setStageFilter}>
              <SelectTrigger className="md:w-[140px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="ALL">All stages</SelectItem>
                {stageOptions.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={orgUnitFilter} onValueChange={setOrgUnitFilter}>
              <SelectTrigger className="md:w-[170px]">
                <SelectValue placeholder="Org unit" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="ALL">All org units</SelectItem>
                {orgUnits.map((unit) => (
                  <SelectItem key={unit.id} value={String(unit.id)}>
                    {unit.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={locationFilter} onValueChange={setLocationFilter}>
              <SelectTrigger className="md:w-[170px]">
                <SelectValue placeholder="Location" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="ALL">All locations</SelectItem>
                {locations.map((item) => (
                  <SelectItem key={item.id} value={String(item.id)}>
                    {item.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button variant="outline" onClick={() => void loadCandidates({ showLoader: true })}>
              Apply
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center gap-2 text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading candidates...
            </div>
          ) : candidates.length ? (
            <Table className="[&_th]:h-10 [&_th]:text-xs [&_th]:uppercase [&_th]:tracking-wide">
              <TableHeader>
                <TableRow>
                  <TableHead>Candidate</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>Org Unit</TableHead>
                  <TableHead>Location</TableHead>
                  <TableHead>Cost Center</TableHead>
                  <TableHead>Hiring Manager</TableHead>
                  <TableHead>Stage</TableHead>
                  <TableHead>Expected Join</TableHead>
                  <TableHead>Owner</TableHead>
                  <TableHead className="text-right">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {candidates.map((candidate) => (
                  <TableRow key={candidate.id}>
                    <TableCell>{candidate.full_name}</TableCell>
                    <TableCell>{candidate.role_applied}</TableCell>
                    <TableCell>{candidate.org_unit_name || "-"}</TableCell>
                    <TableCell>{candidate.location_name || "-"}</TableCell>
                    <TableCell>{candidate.cost_center_code || "-"}</TableCell>
                    <TableCell>{candidate.hiring_manager_name || "-"}</TableCell>
                    <TableCell>
                      <Select value={candidate.stage} onValueChange={(value) => void updateCandidateStage(candidate.id, value)}>
                        <SelectTrigger className="h-8 w-[150px]">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {stageOptions.map((option) => (
                            <SelectItem key={option.value} value={option.value}>
                              {option.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </TableCell>
                    <TableCell>{candidate.expected_join || "-"}</TableCell>
                    <TableCell>
                      {candidate.owner_name || (candidate.owner ? ownerLabelById.get(candidate.owner) : "") || "Unassigned"}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button variant="ghost" size="icon" onClick={() => void deleteCandidate(candidate.id)}>
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <p className="text-sm text-muted-foreground">No candidates found.</p>
          )}
          {candidateLoading ? (
            <div className="mt-3 flex items-center gap-2 text-xs text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Refreshing candidates...
            </div>
          ) : null}
        </CardContent>
      </Card>
    </AppShell>
  );
}
