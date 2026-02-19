"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, Plus } from "lucide-react";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { API_BASE_URL, apiFetch, readJsonSafely } from "@/lib/api";
import {
  getAccessToken,
  getAuthUser,
  getSelectedOrganizationId,
  isAdminOrHR,
  setSelectedOrganization as persistSelectedOrganization,
} from "@/lib/auth";

type OrgUnit = { id: number; name: string; unit_type: string; parent_name: string };
type Location = { id: number; name: string; country: string; city: string };
type CostCenter = { id: number; code: string; name: string };
type JobLevel = { id: number; name: string };
type Position = { id: number; title: string; org_unit_name: string; location_name: string; cost_center_code: string; job_level_name: string };
type EmployeeRecord = { id: number; user_name: string; user_email: string; position_title: string; status: string; current_manager_employee_id: number | null };
type ReportingNode = { employee_id: number; name: string; position_title: string; children: ReportingNode[] };
type ReportingPayload = { employee: ReportingNode; manager_chain: Array<{ employee_id: number; name: string; position_title: string }> };
type FormFieldDef = {
  id: number;
  module: "TALENT" | "ONBOARDING";
  key: string;
  label: string;
  field_type: string;
  required: boolean;
  active: boolean;
  options: string[];
  org_unit: number | null;
  org_unit_name: string;
  location: number | null;
  location_name: string;
  sort_order: number;
  placeholder: string;
  help_text: string;
};
type CompanyOption = { id: number; name: string; slug: string };
type CompanyDirectoryPayload = { selected_company_id: number | null; results: CompanyOption[] };
type TenantRow = {
  id: number;
  company: number;
  directory_name: string;
  schema_name: string;
  domain: string;
  active: boolean;
};

function TreeNode({ node }: { node: ReportingNode }) {
  return (
    <li className="space-y-2">
      <div className="rounded-md border border-border/60 bg-card/70 px-3 py-2 text-sm">
        <span className="font-medium">{node.name}</span>
        <span className="ml-2 text-muted-foreground">({node.position_title})</span>
      </div>
      {node.children.length ? (
        <ul className="ml-4 space-y-2 border-l border-border/50 pl-4">
          {node.children.map((child) => (
            <TreeNode key={child.employee_id} node={child} />
          ))}
        </ul>
      ) : null}
    </li>
  );
}

async function detailMessage(response: Response, fallback: string) {
  const parsed = await readJsonSafely<{ detail?: string }>(response);
  return parsed?.detail || fallback;
}

export default function OrganizationPage() {
  const router = useRouter();
  const authUser = getAuthUser();

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [orgUnits, setOrgUnits] = useState<OrgUnit[]>([]);
  const [locations, setLocations] = useState<Location[]>([]);
  const [costCenters, setCostCenters] = useState<CostCenter[]>([]);
  const [jobLevels, setJobLevels] = useState<JobLevel[]>([]);
  const [positions, setPositions] = useState<Position[]>([]);
  const [employees, setEmployees] = useState<EmployeeRecord[]>([]);
  const [reporting, setReporting] = useState<ReportingPayload | null>(null);
  const [formFields, setFormFields] = useState<FormFieldDef[]>([]);
  const [builderModule, setBuilderModule] = useState<"TALENT" | "ONBOARDING">("TALENT");
  const [companies, setCompanies] = useState<CompanyOption[]>([]);
  const [selectedCompanyId, setSelectedCompanyId] = useState("");
  const [companyNameInput, setCompanyNameInput] = useState("");
  const [loadingCompanies, setLoadingCompanies] = useState(false);
  const [tenants, setTenants] = useState<TenantRow[]>([]);
  const [newOrganization, setNewOrganization] = useState({
    name: "",
    slug: "",
    schema_name: "",
    domain: "",
  });

  const [newUnit, setNewUnit] = useState({ name: "", unit_type: "DEPARTMENT", parent: "none" });
  const [newLocation, setNewLocation] = useState({ name: "", country: "", city: "", timezone: "UTC" });
  const [newPosition, setNewPosition] = useState({
    title: "",
    org_unit: "none",
    location: "none",
    cost_center: "none",
    job_level: "none",
    manager_position: "none",
    headcount: "1",
  });
  const [managerChange, setManagerChange] = useState({ employee_id: "none", manager_employee_id: "none", effective_from: "", note: "" });
  const [reportingEmployee, setReportingEmployee] = useState("none");
  const [newFormField, setNewFormField] = useState({
    module: "TALENT" as "TALENT" | "ONBOARDING",
    key: "",
    label: "",
    field_type: "TEXT",
    required: false,
    active: true,
    sort_order: "100",
    org_unit: "none",
    location: "none",
    options_text: "",
    placeholder: "",
    help_text: "",
  });
  const selectedCompany = companies.find((item) => String(item.id) === selectedCompanyId) || null;
  const actorIsAdmin = Boolean(authUser?.is_admin);
  const organizationServerUrl = selectedCompany
    ? `${API_BASE_URL.replace(/\/api$/i, "")}/login/?company_name=${encodeURIComponent(selectedCompany.name)}&next=/dashboard/`
    : `${API_BASE_URL.replace(/\/api$/i, "")}/login/?next=/dashboard/`;

  const managerLabel = (id: number | null) => {
    if (!id) return "-";
    const found = employees.find((employee) => employee.id === id);
    return found?.user_name || `Employee #${id}`;
  };

  async function loadFormFields(module: "TALENT" | "ONBOARDING" = builderModule) {
    const response = await apiFetch(`/org/form-fields/?module=${module}&include_inactive=true&scoped=false`);
    if (!response.ok) {
      throw new Error("Failed to load form builder fields.");
    }
    const payload = (await response.json()) as FormFieldDef[];
    setFormFields(payload);
  }

  async function loadAll() {
    setLoading(true);
    try {
      const [units, locs, centers, levels, pos, emp] = await Promise.all([
        apiFetch("/org/units/"),
        apiFetch("/org/locations/"),
        apiFetch("/org/cost-centers/"),
        apiFetch("/org/job-levels/"),
        apiFetch("/org/positions/"),
        apiFetch("/hr/employees/"),
      ]);
      if (!units.ok || !locs.ok || !centers.ok || !levels.ok || !pos.ok || !emp.ok) {
        throw new Error("Failed to load organization data.");
      }
      setOrgUnits((await units.json()) as OrgUnit[]);
      setLocations((await locs.json()) as Location[]);
      setCostCenters((await centers.json()) as CostCenter[]);
      setJobLevels((await levels.json()) as JobLevel[]);
      setPositions((await pos.json()) as Position[]);
      setEmployees((await emp.json()) as EmployeeRecord[]);
      await loadFormFields(builderModule);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to load organization data.");
    } finally {
      setLoading(false);
    }
  }

  async function addOrgUnit() {
    if (!newUnit.name.trim()) {
      toast.error("Org unit name is required.");
      return;
    }
    setSaving(true);
    try {
      const response = await apiFetch("/org/units/", {
        method: "POST",
        body: JSON.stringify({
          name: newUnit.name.trim(),
          unit_type: newUnit.unit_type,
          parent: newUnit.parent === "none" ? null : Number(newUnit.parent),
        }),
      });
      if (!response.ok) throw new Error(await detailMessage(response, "Could not create org unit."));
      toast.success("Org unit created.");
      setNewUnit({ name: "", unit_type: "DEPARTMENT", parent: "none" });
      await loadAll();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not create org unit.");
    } finally {
      setSaving(false);
    }
  }

  async function loadCompanies() {
    setLoadingCompanies(true);
    try {
      const response = await apiFetch("/org/companies/", { withTenant: false });
      const payload = await readJsonSafely<CompanyDirectoryPayload>(response);
      if (!response.ok || !payload) {
        throw new Error("Failed to load companies.");
      }
      const options = payload.results || [];
      setCompanies(options);
      const storedId = getSelectedOrganizationId();
      const fallbackId = payload.selected_company_id ? String(payload.selected_company_id) : "";
      const validStored = options.some((item) => String(item.id) === storedId);
      const nextId = (validStored ? storedId : "") || fallbackId || (options[0] ? String(options[0].id) : "");
      setSelectedCompanyId(nextId);
      const selected = options.find((item) => String(item.id) === nextId);
      if (selected) {
        persistSelectedOrganization({ id: selected.id, slug: selected.slug });
        setCompanyNameInput(selected.name);
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to load companies.");
    } finally {
      setLoadingCompanies(false);
    }
  }

  async function loadTenants() {
    if (!actorIsAdmin) return;
    try {
      const response = await apiFetch("/org/tenants/", { withTenant: false });
      if (!response.ok) {
        throw new Error("Failed to load tenant records.");
      }
      const payload = (await response.json()) as TenantRow[];
      setTenants(payload);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to load tenant records.");
    }
  }

  async function addOrganization() {
    if (!actorIsAdmin) {
      toast.error("Only platform admin can add organizations.");
      return;
    }
    if (!newOrganization.name.trim() || !newOrganization.slug.trim() || !newOrganization.schema_name.trim() || !newOrganization.domain.trim()) {
      toast.error("Name, slug, schema name, and domain are required.");
      return;
    }
    setSaving(true);
    try {
      const response = await apiFetch("/org/companies/", {
        method: "POST",
        withTenant: false,
        body: JSON.stringify({
          name: newOrganization.name.trim(),
          slug: newOrganization.slug.trim().toLowerCase(),
          schema_name: newOrganization.schema_name.trim().toLowerCase(),
          domain: newOrganization.domain.trim().toLowerCase(),
        }),
      });
      const payload = await readJsonSafely<{ detail?: string; company?: CompanyOption }>(response);
      if (!response.ok) {
        throw new Error(payload?.detail || "Could not create organization.");
      }
      toast.success("Organization and tenant created.");
      setNewOrganization({ name: "", slug: "", schema_name: "", domain: "" });
      await loadCompanies();
      await loadTenants();
      if (payload?.company?.id && payload.company.slug) {
        setSelectedCompanyId(String(payload.company.id));
        persistSelectedOrganization({ id: payload.company.id, slug: payload.company.slug });
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not create organization.");
    } finally {
      setSaving(false);
    }
  }

  async function addLocation() {
    if (!newLocation.name.trim()) {
      toast.error("Location name is required.");
      return;
    }
    setSaving(true);
    try {
      const response = await apiFetch("/org/locations/", {
        method: "POST",
        body: JSON.stringify({
          name: newLocation.name.trim(),
          country: newLocation.country.trim(),
          city: newLocation.city.trim(),
          timezone: newLocation.timezone.trim() || "UTC",
          active: true,
        }),
      });
      if (!response.ok) throw new Error(await detailMessage(response, "Could not create location."));
      toast.success("Location created.");
      setNewLocation({ name: "", country: "", city: "", timezone: "UTC" });
      await loadAll();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not create location.");
    } finally {
      setSaving(false);
    }
  }

  async function addPosition() {
    if (!newPosition.title.trim() || newPosition.org_unit === "none" || newPosition.location === "none" || newPosition.cost_center === "none" || newPosition.job_level === "none") {
      toast.error("Title, org unit, location, cost center, and job level are required.");
      return;
    }
    setSaving(true);
    try {
      const response = await apiFetch("/org/positions/", {
        method: "POST",
        body: JSON.stringify({
          title: newPosition.title.trim(),
          org_unit: Number(newPosition.org_unit),
          location: Number(newPosition.location),
          cost_center: Number(newPosition.cost_center),
          job_level: Number(newPosition.job_level),
          manager_position: newPosition.manager_position === "none" ? null : Number(newPosition.manager_position),
          headcount: Number(newPosition.headcount || "1"),
        }),
      });
      if (!response.ok) throw new Error(await detailMessage(response, "Could not create position."));
      toast.success("Position created.");
      setNewPosition({ title: "", org_unit: "none", location: "none", cost_center: "none", job_level: "none", manager_position: "none", headcount: "1" });
      await loadAll();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not create position.");
    } finally {
      setSaving(false);
    }
  }

  async function applyManagerChange() {
    if (managerChange.employee_id === "none") {
      toast.error("Select an employee.");
      return;
    }
    setSaving(true);
    try {
      const response = await apiFetch("/org/reporting/change-manager", {
        method: "POST",
        body: JSON.stringify({
          employee_id: Number(managerChange.employee_id),
          manager_employee_id: managerChange.manager_employee_id === "none" ? null : Number(managerChange.manager_employee_id),
          effective_from: managerChange.effective_from || undefined,
          note: managerChange.note.trim(),
        }),
      });
      if (!response.ok) throw new Error(await detailMessage(response, "Could not update manager."));
      toast.success("Manager updated.");
      await loadAll();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not update manager.");
    } finally {
      setSaving(false);
    }
  }

  async function loadTree() {
    if (reportingEmployee === "none") {
      toast.error("Select an employee.");
      return;
    }
    try {
      const response = await apiFetch(`/org/reporting/tree?employee_id=${reportingEmployee}`);
      if (!response.ok) throw new Error(await detailMessage(response, "Could not load reporting tree."));
      setReporting((await response.json()) as ReportingPayload);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not load reporting tree.");
    }
  }

  async function addFormField() {
    if (!newFormField.key.trim() || !newFormField.label.trim()) {
      toast.error("Field key and label are required.");
      return;
    }
    setSaving(true);
    try {
      const response = await apiFetch("/org/form-fields/", {
        method: "POST",
        body: JSON.stringify({
          module: newFormField.module,
          key: newFormField.key.trim().toLowerCase(),
          label: newFormField.label.trim(),
          field_type: newFormField.field_type,
          required: newFormField.required,
          active: newFormField.active,
          sort_order: Number(newFormField.sort_order || "100"),
          org_unit: newFormField.org_unit === "none" ? null : Number(newFormField.org_unit),
          location: newFormField.location === "none" ? null : Number(newFormField.location),
          options: newFormField.options_text,
          placeholder: newFormField.placeholder.trim(),
          help_text: newFormField.help_text.trim(),
        }),
      });
      if (!response.ok) throw new Error(await detailMessage(response, "Could not create form field."));
      toast.success("Form field created.");
      setNewFormField((prev) => ({
        ...prev,
        key: "",
        label: "",
        options_text: "",
        placeholder: "",
        help_text: "",
      }));
      await loadFormFields(builderModule);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not create form field.");
    } finally {
      setSaving(false);
    }
  }

  async function toggleFormFieldActive(field: FormFieldDef) {
    setSaving(true);
    try {
      const response = await apiFetch(`/org/form-fields/${field.id}/`, {
        method: "PATCH",
        body: JSON.stringify({ active: !field.active }),
      });
      if (!response.ok) throw new Error(await detailMessage(response, "Could not update form field."));
      toast.success("Form field updated.");
      await loadFormFields(builderModule);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not update form field.");
    } finally {
      setSaving(false);
    }
  }

  async function deleteFormField(id: number) {
    setSaving(true);
    try {
      const response = await apiFetch(`/org/form-fields/${id}/`, { method: "DELETE" });
      if (!response.ok && response.status !== 204) throw new Error("Could not delete form field.");
      toast.success("Form field deleted.");
      await loadFormFields(builderModule);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not delete form field.");
    } finally {
      setSaving(false);
    }
  }

  useEffect(() => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    if (!isAdminOrHR(authUser)) {
      router.replace("/dashboard");
      return;
    }
    async function init() {
      await loadCompanies();
      if (actorIsAdmin) {
        await loadTenants();
      }
      await loadAll();
    }
    void init();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router, actorIsAdmin]);

  useEffect(() => {
    if (!getAccessToken()) return;
    void loadFormFields(builderModule);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [builderModule]);

  function onCompanyChange(value: string) {
    setSelectedCompanyId(value);
    const selected = companies.find((item) => String(item.id) === value);
    if (!selected) return;
    persistSelectedOrganization({ id: selected.id, slug: selected.slug });
    setCompanyNameInput(selected.name);
    void loadAll();
  }

  function applyCompanyByName() {
    const typed = companyNameInput.trim().toLowerCase();
    if (!typed) {
      toast.error("Type a company name first.");
      return;
    }
    const match = companies.find((item) => item.name.trim().toLowerCase() === typed);
    if (!match) {
      toast.error("Company name not found. Use exact company name.");
      return;
    }
    setSelectedCompanyId(String(match.id));
    persistSelectedOrganization({ id: match.id, slug: match.slug });
    toast.success(`Company selected: ${match.name}`);
    void loadAll();
  }

  return (
    <AppShell>
      <PageHeader
        title="Organization Workspace"
        description="Company-specific directory, positions, employees, reporting hierarchy, and form builder."
        badge={<Badge variant="outline">HR / Admin</Badge>}
      />
      <Card className="surface-card mb-6">
        <CardHeader>
          <CardTitle>Organization Context (Company Based)</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-4">
          <div className="md:col-span-2">
            <Label className="mb-1 block text-xs">Select Company</Label>
            <Select value={selectedCompanyId} onValueChange={onCompanyChange} disabled={loadingCompanies}>
              <SelectTrigger>
                <SelectValue placeholder={loadingCompanies ? "Loading companies..." : "Select company"} />
              </SelectTrigger>
              <SelectContent>
                {companies.map((company) => (
                  <SelectItem key={company.id} value={String(company.id)}>
                    {company.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center">
            <Badge variant="secondary" className="truncate">
              {selectedCompany ? `Active: ${selectedCompany.name}` : "No company selected"}
            </Badge>
          </div>
          <Button
            variant="outline"
            onClick={() => {
              if (typeof window !== "undefined") {
                window.location.href = organizationServerUrl;
              }
            }}
          >
            Organization Server Login
          </Button>
          <div className="md:col-span-3">
            <Label className="mb-1 block text-xs">Type Company Name (for first-time org login)</Label>
            <Input
              placeholder="Enter exact company name"
              value={companyNameInput}
              onChange={(event) => setCompanyNameInput(event.target.value)}
            />
          </div>
          <Button variant="secondary" onClick={applyCompanyByName}>
            Apply Company Name
          </Button>
        </CardContent>
      </Card>
      <Tabs
        defaultValue={actorIsAdmin ? "organizations" : "directory"}
        className="grid gap-6 lg:grid-cols-[250px_minmax(0,1fr)]"
      >
        <Card className="surface-card h-fit">
          <CardHeader>
            <CardTitle>Organization Sidebar</CardTitle>
          </CardHeader>
          <CardContent className="p-2">
            <TabsList className="grid h-auto w-full grid-cols-1 gap-1 bg-transparent p-0">
              {actorIsAdmin ? (
                <TabsTrigger
                  value="organizations"
                  className="w-full justify-start rounded-md px-3 py-2 text-left data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
                >
                  Organizations
                </TabsTrigger>
              ) : null}
              <TabsTrigger
                value="directory"
                className="w-full justify-start rounded-md px-3 py-2 text-left data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
              >
                Directory
              </TabsTrigger>
              <TabsTrigger
                value="positions"
                className="w-full justify-start rounded-md px-3 py-2 text-left data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
              >
                Positions
              </TabsTrigger>
              <TabsTrigger
                value="employees"
                className="w-full justify-start rounded-md px-3 py-2 text-left data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
              >
                Employees
              </TabsTrigger>
              <TabsTrigger
                value="reporting"
                className="w-full justify-start rounded-md px-3 py-2 text-left data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
              >
                Reporting
              </TabsTrigger>
              <TabsTrigger
                value="form-builder"
                className="w-full justify-start rounded-md px-3 py-2 text-left data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
              >
                Form Builder
              </TabsTrigger>
            </TabsList>
          </CardContent>
        </Card>

        <div className="space-y-6">
        {actorIsAdmin ? (
          <TabsContent value="organizations" className="space-y-6">
            <Card className="surface-card">
              <CardHeader>
                <CardTitle>Add Another Organization + Tenant</CardTitle>
              </CardHeader>
              <CardContent className="grid gap-3 md:grid-cols-5">
                <Input
                  placeholder="Organization name"
                  value={newOrganization.name}
                  onChange={(event) => setNewOrganization((prev) => ({ ...prev, name: event.target.value }))}
                />
                <Input
                  placeholder="Slug (example: acme)"
                  value={newOrganization.slug}
                  onChange={(event) => setNewOrganization((prev) => ({ ...prev, slug: event.target.value }))}
                />
                <Input
                  placeholder="Schema name (example: acme)"
                  value={newOrganization.schema_name}
                  onChange={(event) => setNewOrganization((prev) => ({ ...prev, schema_name: event.target.value }))}
                />
                <Input
                  placeholder="Domain (example: acme.leave.local)"
                  value={newOrganization.domain}
                  onChange={(event) => setNewOrganization((prev) => ({ ...prev, domain: event.target.value }))}
                />
                <Button onClick={addOrganization} disabled={saving}>
                  {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Plus className="mr-2 h-4 w-4" />}
                  Add
                </Button>
              </CardContent>
            </Card>
            <Card className="surface-card">
              <CardHeader>
                <CardTitle>Tenant Mapping</CardTitle>
              </CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Organization</TableHead>
                      <TableHead>Schema</TableHead>
                      <TableHead>Domain</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {tenants.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={3}>No tenant records found.</TableCell>
                      </TableRow>
                    ) : (
                      tenants.map((row) => (
                        <TableRow key={row.id}>
                          <TableCell>{row.directory_name || `Company #${row.company}`}</TableCell>
                          <TableCell>{row.schema_name}</TableCell>
                          <TableCell>{row.domain}</TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </TabsContent>
        ) : null}
        <TabsContent value="directory" className="space-y-6">
          <Card className="surface-card">
            <CardHeader><CardTitle>Create Org Unit</CardTitle></CardHeader>
            <CardContent className="grid gap-3 md:grid-cols-4">
              <Input placeholder="Unit name" value={newUnit.name} onChange={(event) => setNewUnit((prev) => ({ ...prev, name: event.target.value }))} />
              <Select value={newUnit.unit_type} onValueChange={(value) => setNewUnit((prev) => ({ ...prev, unit_type: value }))}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="DEPARTMENT">Department</SelectItem><SelectItem value="TEAM">Team</SelectItem></SelectContent></Select>
              <Select value={newUnit.parent} onValueChange={(value) => setNewUnit((prev) => ({ ...prev, parent: value }))}><SelectTrigger><SelectValue placeholder="Parent (optional)" /></SelectTrigger><SelectContent><SelectItem value="none">No parent</SelectItem>{orgUnits.map((unit) => (<SelectItem key={unit.id} value={String(unit.id)}>{unit.name}</SelectItem>))}</SelectContent></Select>
              <Button onClick={addOrgUnit} disabled={saving}>{saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Plus className="mr-2 h-4 w-4" />}Add Unit</Button>
            </CardContent>
          </Card>
          <Card className="surface-card">
            <CardHeader><CardTitle>Create Location (Manual Entry)</CardTitle></CardHeader>
            <CardContent className="grid gap-3 md:grid-cols-5">
              <Input
                placeholder="Location name"
                value={newLocation.name}
                onChange={(event) => setNewLocation((prev) => ({ ...prev, name: event.target.value }))}
              />
              <Input
                placeholder="Country"
                value={newLocation.country}
                onChange={(event) => setNewLocation((prev) => ({ ...prev, country: event.target.value }))}
              />
              <Input
                placeholder="City"
                value={newLocation.city}
                onChange={(event) => setNewLocation((prev) => ({ ...prev, city: event.target.value }))}
              />
              <Input
                placeholder="Timezone (default UTC)"
                value={newLocation.timezone}
                onChange={(event) => setNewLocation((prev) => ({ ...prev, timezone: event.target.value }))}
              />
              <Button onClick={addLocation} disabled={saving}>
                {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Plus className="mr-2 h-4 w-4" />}
                Add Location
              </Button>
            </CardContent>
          </Card>
          <div className="grid gap-6 lg:grid-cols-2">
            <Card className="surface-card"><CardHeader><CardTitle>Org Units</CardTitle></CardHeader><CardContent><Table><TableHeader><TableRow><TableHead>Name</TableHead><TableHead>Type</TableHead><TableHead>Parent</TableHead></TableRow></TableHeader><TableBody>{orgUnits.map((unit) => (<TableRow key={unit.id}><TableCell>{unit.name}</TableCell><TableCell>{unit.unit_type}</TableCell><TableCell>{unit.parent_name || "-"}</TableCell></TableRow>))}</TableBody></Table></CardContent></Card>
            <Card className="surface-card"><CardHeader><CardTitle>Locations</CardTitle></CardHeader><CardContent><Table><TableHeader><TableRow><TableHead>Name</TableHead><TableHead>Country</TableHead><TableHead>City</TableHead></TableRow></TableHeader><TableBody>{locations.map((item) => (<TableRow key={item.id}><TableCell>{item.name}</TableCell><TableCell>{item.country || "-"}</TableCell><TableCell>{item.city || "-"}</TableCell></TableRow>))}</TableBody></Table></CardContent></Card>
          </div>
          <div className="grid gap-6 lg:grid-cols-2">
            <Card className="surface-card"><CardHeader><CardTitle>Cost Centers</CardTitle></CardHeader><CardContent><Table><TableHeader><TableRow><TableHead>Code</TableHead><TableHead>Name</TableHead></TableRow></TableHeader><TableBody>{costCenters.map((item) => (<TableRow key={item.id}><TableCell>{item.code}</TableCell><TableCell>{item.name}</TableCell></TableRow>))}</TableBody></Table></CardContent></Card>
            <Card className="surface-card"><CardHeader><CardTitle>Job Levels</CardTitle></CardHeader><CardContent><Table><TableHeader><TableRow><TableHead>Name</TableHead></TableRow></TableHeader><TableBody>{jobLevels.map((item) => (<TableRow key={item.id}><TableCell>{item.name}</TableCell></TableRow>))}</TableBody></Table></CardContent></Card>
          </div>
        </TabsContent>
        <TabsContent value="positions">
          <Card className="surface-card">
            <CardHeader><CardTitle>Create Position</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                <Input placeholder="Title" value={newPosition.title} onChange={(event) => setNewPosition((prev) => ({ ...prev, title: event.target.value }))} />
                <Select value={newPosition.org_unit} onValueChange={(value) => setNewPosition((prev) => ({ ...prev, org_unit: value }))}><SelectTrigger><SelectValue placeholder="Org unit" /></SelectTrigger><SelectContent><SelectItem value="none">Select org unit</SelectItem>{orgUnits.map((unit) => (<SelectItem key={unit.id} value={String(unit.id)}>{unit.name}</SelectItem>))}</SelectContent></Select>
                <Select value={newPosition.location} onValueChange={(value) => setNewPosition((prev) => ({ ...prev, location: value }))}><SelectTrigger><SelectValue placeholder="Location" /></SelectTrigger><SelectContent><SelectItem value="none">Select location</SelectItem>{locations.map((item) => (<SelectItem key={item.id} value={String(item.id)}>{item.name}</SelectItem>))}</SelectContent></Select>
                <Select value={newPosition.cost_center} onValueChange={(value) => setNewPosition((prev) => ({ ...prev, cost_center: value }))}><SelectTrigger><SelectValue placeholder="Cost center" /></SelectTrigger><SelectContent><SelectItem value="none">Select cost center</SelectItem>{costCenters.map((item) => (<SelectItem key={item.id} value={String(item.id)}>{item.code}</SelectItem>))}</SelectContent></Select>
                <Select value={newPosition.job_level} onValueChange={(value) => setNewPosition((prev) => ({ ...prev, job_level: value }))}><SelectTrigger><SelectValue placeholder="Job level" /></SelectTrigger><SelectContent><SelectItem value="none">Select job level</SelectItem>{jobLevels.map((item) => (<SelectItem key={item.id} value={String(item.id)}>{item.name}</SelectItem>))}</SelectContent></Select>
                <Select value={newPosition.manager_position} onValueChange={(value) => setNewPosition((prev) => ({ ...prev, manager_position: value }))}><SelectTrigger><SelectValue placeholder="Manager position (optional)" /></SelectTrigger><SelectContent><SelectItem value="none">None</SelectItem>{positions.map((item) => (<SelectItem key={item.id} value={String(item.id)}>{item.title}</SelectItem>))}</SelectContent></Select>
                <Input type="number" min={1} value={newPosition.headcount} onChange={(event) => setNewPosition((prev) => ({ ...prev, headcount: event.target.value }))} />
                <Button onClick={addPosition} disabled={saving}><Plus className="mr-2 h-4 w-4" />Add Position</Button>
              </div>
              <Table>
                <TableHeader><TableRow><TableHead>Title</TableHead><TableHead>Org Unit</TableHead><TableHead>Location</TableHead><TableHead>Cost Center</TableHead><TableHead>Job Level</TableHead></TableRow></TableHeader>
                <TableBody>{positions.map((position) => (<TableRow key={position.id}><TableCell>{position.title}</TableCell><TableCell>{position.org_unit_name}</TableCell><TableCell>{position.location_name}</TableCell><TableCell>{position.cost_center_code}</TableCell><TableCell>{position.job_level_name}</TableCell></TableRow>))}</TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="employees" className="space-y-6">
          <Card className="surface-card">
            <CardHeader><CardTitle>Change Manager</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                <Select value={managerChange.employee_id} onValueChange={(value) => setManagerChange((prev) => ({ ...prev, employee_id: value }))}><SelectTrigger><SelectValue placeholder="Employee" /></SelectTrigger><SelectContent><SelectItem value="none">Select employee</SelectItem>{employees.map((employee) => (<SelectItem key={employee.id} value={String(employee.id)}>{employee.user_name || `Employee #${employee.id}`}</SelectItem>))}</SelectContent></Select>
                <Select value={managerChange.manager_employee_id} onValueChange={(value) => setManagerChange((prev) => ({ ...prev, manager_employee_id: value }))}><SelectTrigger><SelectValue placeholder="Manager" /></SelectTrigger><SelectContent><SelectItem value="none">No manager</SelectItem>{employees.map((employee) => (<SelectItem key={employee.id} value={String(employee.id)}>{employee.user_name || `Employee #${employee.id}`}</SelectItem>))}</SelectContent></Select>
                <Input type="date" value={managerChange.effective_from} onChange={(event) => setManagerChange((prev) => ({ ...prev, effective_from: event.target.value }))} />
                <Button onClick={applyManagerChange} disabled={saving}>Apply</Button>
              </div>
              <Textarea placeholder="Optional note" value={managerChange.note} onChange={(event) => setManagerChange((prev) => ({ ...prev, note: event.target.value }))} />
            </CardContent>
          </Card>
          <Card className="surface-card">
            <CardHeader><CardTitle>Employee Records</CardTitle></CardHeader>
            <CardContent>
              <Table>
                <TableHeader><TableRow><TableHead>Employee</TableHead><TableHead>Email</TableHead><TableHead>Position</TableHead><TableHead>Status</TableHead><TableHead>Manager</TableHead></TableRow></TableHeader>
                <TableBody>{employees.map((employee) => (<TableRow key={employee.id}><TableCell>{employee.user_name || `Employee #${employee.id}`}</TableCell><TableCell>{employee.user_email || "-"}</TableCell><TableCell>{employee.position_title}</TableCell><TableCell>{employee.status}</TableCell><TableCell>{managerLabel(employee.current_manager_employee_id)}</TableCell></TableRow>))}</TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="reporting">
          <Card className="surface-card">
            <CardHeader><CardTitle>Reporting Tree</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-col gap-3 md:flex-row">
                <Select value={reportingEmployee} onValueChange={setReportingEmployee}>
                  <SelectTrigger className="md:w-[320px]"><SelectValue placeholder="Select employee" /></SelectTrigger>
                  <SelectContent><SelectItem value="none">Select employee</SelectItem>{employees.map((employee) => (<SelectItem key={employee.id} value={String(employee.id)}>{employee.user_name || `Employee #${employee.id}`}</SelectItem>))}</SelectContent>
                </Select>
                <Button onClick={() => void loadTree()}>Load Tree</Button>
              </div>
              {reporting ? (
                <div className="space-y-4">
                  <div className="flex flex-wrap gap-2">
                    {reporting.manager_chain.map((manager) => (
                      <Badge key={manager.employee_id} variant="secondary">{manager.name}</Badge>
                    ))}
                  </div>
                  <ul className="space-y-2">
                    <TreeNode node={reporting.employee} />
                  </ul>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">Select employee and load reporting tree.</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="form-builder" className="space-y-6">
          <Card className="surface-card">
            <CardHeader>
              <CardTitle>Create Form Field</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                <div>
                  <Label className="mb-1 block">Module</Label>
                  <Select
                    value={newFormField.module}
                    onValueChange={(value) => {
                      const selectedModule = value as "TALENT" | "ONBOARDING";
                      setNewFormField((prev) => ({ ...prev, module: selectedModule }));
                      setBuilderModule(selectedModule);
                    }}
                  >
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="TALENT">Talent Acquisition</SelectItem>
                      <SelectItem value="ONBOARDING">Onboarding</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="mb-1 block">Field Key</Label>
                  <Input
                    placeholder="example: portfolio_url"
                    value={newFormField.key}
                    onChange={(event) => setNewFormField((prev) => ({ ...prev, key: event.target.value }))}
                  />
                </div>
                <div>
                  <Label className="mb-1 block">Label</Label>
                  <Input
                    placeholder="Portfolio URL"
                    value={newFormField.label}
                    onChange={(event) => setNewFormField((prev) => ({ ...prev, label: event.target.value }))}
                  />
                </div>
                <div>
                  <Label className="mb-1 block">Field Type</Label>
                  <Select value={newFormField.field_type} onValueChange={(value) => setNewFormField((prev) => ({ ...prev, field_type: value }))}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="TEXT">Text</SelectItem>
                      <SelectItem value="TEXTAREA">Textarea</SelectItem>
                      <SelectItem value="NUMBER">Number</SelectItem>
                      <SelectItem value="DATE">Date</SelectItem>
                      <SelectItem value="EMAIL">Email</SelectItem>
                      <SelectItem value="PHONE">Phone</SelectItem>
                      <SelectItem value="URL">URL</SelectItem>
                      <SelectItem value="SELECT">Select</SelectItem>
                      <SelectItem value="CHECKBOX">Checkbox</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="mb-1 block">Org Unit Scope</Label>
                  <Select value={newFormField.org_unit} onValueChange={(value) => setNewFormField((prev) => ({ ...prev, org_unit: value }))}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="none">All org units</SelectItem>
                      {orgUnits.map((unit) => (
                        <SelectItem key={unit.id} value={String(unit.id)}>{unit.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="mb-1 block">Location Scope</Label>
                  <Select value={newFormField.location} onValueChange={(value) => setNewFormField((prev) => ({ ...prev, location: value }))}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="none">All locations</SelectItem>
                      {locations.map((location) => (
                        <SelectItem key={location.id} value={String(location.id)}>{location.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="mb-1 block">Sort Order</Label>
                  <Input
                    type="number"
                    min={0}
                    value={newFormField.sort_order}
                    onChange={(event) => setNewFormField((prev) => ({ ...prev, sort_order: event.target.value }))}
                  />
                </div>
                <div className="flex items-end gap-4">
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={newFormField.required}
                      onChange={(event) => setNewFormField((prev) => ({ ...prev, required: event.target.checked }))}
                    />
                    Required
                  </label>
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={newFormField.active}
                      onChange={(event) => setNewFormField((prev) => ({ ...prev, active: event.target.checked }))}
                    />
                    Active
                  </label>
                </div>
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                <div>
                  <Label className="mb-1 block">Placeholder</Label>
                  <Input
                    placeholder="Optional placeholder"
                    value={newFormField.placeholder}
                    onChange={(event) => setNewFormField((prev) => ({ ...prev, placeholder: event.target.value }))}
                  />
                </div>
                <div>
                  <Label className="mb-1 block">Select Options</Label>
                  <Input
                    placeholder="For select fields: option1,option2,option3"
                    value={newFormField.options_text}
                    onChange={(event) => setNewFormField((prev) => ({ ...prev, options_text: event.target.value }))}
                  />
                </div>
              </div>
              <div>
                <Label className="mb-1 block">Help Text</Label>
                <Textarea
                  placeholder="Optional guidance for users"
                  value={newFormField.help_text}
                  onChange={(event) => setNewFormField((prev) => ({ ...prev, help_text: event.target.value }))}
                />
              </div>
              <Button onClick={addFormField} disabled={saving}>
                {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Plus className="mr-2 h-4 w-4" />}
                Add Field
              </Button>
            </CardContent>
          </Card>

          <Card className="surface-card">
            <CardHeader className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <CardTitle>Configured Fields</CardTitle>
              <Select value={builderModule} onValueChange={(value) => setBuilderModule(value as "TALENT" | "ONBOARDING")}>
                <SelectTrigger className="md:w-[220px]"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="TALENT">Talent Acquisition</SelectItem>
                  <SelectItem value="ONBOARDING">Onboarding</SelectItem>
                </SelectContent>
              </Select>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Label</TableHead>
                    <TableHead>Key</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead>Scope</TableHead>
                    <TableHead>Required</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Action</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {formFields
                    .filter((field) => field.module === builderModule)
                    .map((field) => (
                      <TableRow key={field.id}>
                        <TableCell>{field.label}</TableCell>
                        <TableCell>{field.key}</TableCell>
                        <TableCell>{field.field_type}</TableCell>
                        <TableCell>{field.org_unit_name || "All org units"} / {field.location_name || "All locations"}</TableCell>
                        <TableCell>{field.required ? "Yes" : "No"}</TableCell>
                        <TableCell>{field.active ? "Active" : "Inactive"}</TableCell>
                        <TableCell className="space-x-2">
                          <Button variant="outline" size="sm" onClick={() => void toggleFormFieldActive(field)}>
                            {field.active ? "Disable" : "Enable"}
                          </Button>
                          <Button variant="destructive" size="sm" onClick={() => void deleteFormField(field.id)}>
                            Delete
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>
        </div>
      </Tabs>
      {loading ? <div className="mt-4 text-sm text-muted-foreground">Loading organization data...</div> : null}
    </AppShell>
  );
}
