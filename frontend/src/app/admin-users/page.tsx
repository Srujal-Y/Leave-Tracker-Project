"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { KeyRound, Loader2, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiFetch, readJsonSafely } from "@/lib/api";
import {
  getAccessToken,
  getAuthUser,
  getSelectedOrganizationId,
  isAdmin,
  isAdminOrHR,
  setSelectedOrganization as persistSelectedOrganization,
} from "@/lib/auth";

type PortalAccess = "MAIN" | "ORGANIZATION" | "BOTH";

type UserRow = {
  id: number;
  full_name: string;
  username: string;
  email: string;
  role: "EMPLOYEE" | "MANAGER" | "HR" | string;
  organization?: number | null;
  created_by?: number | null;
  created_by_name?: string;
  created_in_organization?: number | null;
  created_in_organization_name?: string;
  is_admin?: boolean;
  portal_access?: PortalAccess | string;
};

type CompanyOption = {
  id: number;
  name: string;
  slug: string;
};

type CompanyDirectoryPayload = {
  selected_company_id: number | null;
  results: CompanyOption[];
};

type AdminAccountRow = {
  id: number;
  user: number;
  organization: number | null;
  level: "PLATFORM" | "ORGANIZATION" | string;
  can_manage_users: boolean;
  can_manage_organizations: boolean;
};

function normalizePortalAccess(value: unknown): PortalAccess {
  const upper = String(value || "").toUpperCase();
  if (upper === "MAIN" || upper === "ORGANIZATION" || upper === "BOTH") return upper;
  return "BOTH";
}

function portalAccessLabel(value: PortalAccess) {
  if (value === "MAIN") return "Main Only";
  if (value === "ORGANIZATION") return "Organization Only";
  return "Both";
}

function normalizeCompanyToken(value: string) {
  return value.trim().toLowerCase().replace(/\s+/g, " ");
}

export default function AdminUsersPage() {
  const router = useRouter();
  const user = getAuthUser();
  const canManage = isAdminOrHR(user);
  const actorIsAdmin = isAdmin(user);

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [loadingCompanies, setLoadingCompanies] = useState(false);
  const [companySaving, setCompanySaving] = useState(false);
  const [search, setSearch] = useState("");
  const [users, setUsers] = useState<UserRow[]>([]);
  const [companies, setCompanies] = useState<CompanyOption[]>([]);
  const [selectedCompanyId, setSelectedCompanyId] = useState("");
  const [newCompanyName, setNewCompanyName] = useState("");
  const [newCompanySlug, setNewCompanySlug] = useState("");

  const [email, setEmail] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [role, setRole] = useState("EMPLOYEE");
  const [hrCompanyName, setHrCompanyName] = useState("");
  const [managerId, setManagerId] = useState("");
  const [portalAccess, setPortalAccess] = useState<PortalAccess>("BOTH");

  const [passwordDialogOpen, setPasswordDialogOpen] = useState(false);
  const [passwordUser, setPasswordUser] = useState<UserRow | null>(null);
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordSaving, setPasswordSaving] = useState(false);
  const [adminAccounts, setAdminAccounts] = useState<AdminAccountRow[]>([]);
  const [adminUserId, setAdminUserId] = useState("");
  const [adminLevel, setAdminLevel] = useState<"PLATFORM" | "ORGANIZATION">("ORGANIZATION");
  const [adminOrgId, setAdminOrgId] = useState("");
  const [adminSaving, setAdminSaving] = useState(false);

  const managers = useMemo(() => users.filter((item) => item.role === "MANAGER"), [users]);
  const selectedCompany = companies.find((item) => String(item.id) === selectedCompanyId) || null;
  const companyNameById = useMemo(() => {
    const map = new Map<number, string>();
    companies.forEach((company) => map.set(company.id, company.name));
    return map;
  }, [companies]);
  const companyByName = useMemo(() => {
    const map = new Map<string, CompanyOption>();
    companies.forEach((company) => {
      map.set(normalizeCompanyToken(company.name), company);
      map.set(normalizeCompanyToken(company.slug), company);
    });
    return map;
  }, [companies]);

  function canSetPassword(target: UserRow) {
    if (target.is_admin) return false;
    if (actorIsAdmin) return true;
    return user?.role === "HR" && target.role === "EMPLOYEE" && !target.is_admin;
  }

  function closePasswordDialog() {
    setPasswordDialogOpen(false);
    setPasswordUser(null);
    setNewPassword("");
    setConfirmPassword("");
    setPasswordSaving(false);
  }

  function openPasswordDialog(target: UserRow) {
    setPasswordUser(target);
    setNewPassword("");
    setConfirmPassword("");
    setPasswordDialogOpen(true);
  }

  async function loadCompanies() {
    setLoadingCompanies(true);
    try {
      const response = await apiFetch("/org/companies/", { withTenant: false });
      const payload = await readJsonSafely<CompanyDirectoryPayload>(response);
      if (!response.ok || !payload) {
        throw new Error("Could not load companies.");
      }
      const options = payload.results || [];
      setCompanies(options);

      const storedCompanyId = getSelectedOrganizationId();
      const fallbackId = payload.selected_company_id ? String(payload.selected_company_id) : "";
      const validStored = options.some((item) => String(item.id) === storedCompanyId);
      const nextId = (validStored ? storedCompanyId : "") || fallbackId || (options[0] ? String(options[0].id) : "");

      setSelectedCompanyId(nextId);
      const selected = options.find((item) => String(item.id) === nextId);
      if (selected) {
        persistSelectedOrganization({ id: selected.id, slug: selected.slug });
      }
      return nextId;
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not load companies.");
      return "";
    } finally {
      setLoadingCompanies(false);
    }
  }

  async function loadUsers(query = "") {
    setLoading(true);
    try {
      const path = `/admin/users/${query.trim() ? `?q=${encodeURIComponent(query.trim())}` : ""}`;
      const response = await apiFetch(path);
      if (!response.ok) {
        throw new Error("Could not load users");
      }
      const payload = (await response.json()) as UserRow[];
      setUsers(payload);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not load users");
    } finally {
      setLoading(false);
    }
  }

  async function loadAdminAccounts() {
    if (!actorIsAdmin) return;
    try {
      const response = await apiFetch("/admin/accounts/");
      if (!response.ok) {
        throw new Error("Could not load admin accounts.");
      }
      const payload = (await response.json()) as AdminAccountRow[];
      setAdminAccounts(payload);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not load admin accounts.");
    }
  }

  async function createAdminAccount() {
    if (!adminUserId) {
      toast.error("Select a user.");
      return;
    }
    if (adminLevel === "ORGANIZATION" && !adminOrgId) {
      toast.error("Select organization for organization admin.");
      return;
    }
    setAdminSaving(true);
    try {
      const response = await apiFetch("/admin/accounts/", {
        method: "POST",
        body: JSON.stringify({
          user: Number(adminUserId),
          level: adminLevel,
          organization: adminLevel === "ORGANIZATION" ? Number(adminOrgId) : null,
          can_manage_users: true,
          can_manage_organizations: adminLevel === "PLATFORM",
        }),
      });
      const payload = await readJsonSafely<{ detail?: string }>(response);
      if (!response.ok) {
        throw new Error(payload?.detail || "Could not create admin account.");
      }
      toast.success("Admin account updated.");
      await loadAdminAccounts();
      await loadUsers(search);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not create admin account.");
    } finally {
      setAdminSaving(false);
    }
  }

  async function createUser() {
    let createCompanyId = selectedCompanyId;
    const typedCompanyName = hrCompanyName.trim();
    if (role === "HR") {
      if (!typedCompanyName) {
        toast.error("Type company name for HR assignment.");
        return;
      }
      const typedName = normalizeCompanyToken(typedCompanyName);
      const matchedCompany = companyByName.get(typedName);
      createCompanyId = matchedCompany ? String(matchedCompany.id) : "";
      if (!createCompanyId) {
        toast.error("Company name not found. Add the company first in Company Assignment Context.");
        return;
      }
    }
    if (!createCompanyId && role !== "HR") {
      toast.error("Select a company first.");
      return;
    }
    setSaving(true);
    try {
      const response = await apiFetch("/admin/users/", {
        method: "POST",
        withTenant: false,
        body: JSON.stringify({
          company_id: createCompanyId ? Number(createCompanyId) : null,
          company_name: role === "HR" ? typedCompanyName : null,
          email,
          first_name: firstName,
          last_name: lastName,
          role,
          portal_access: portalAccess,
          manager: role === "EMPLOYEE" ? managerId || null : null,
        }),
      });
      const payload = await readJsonSafely<{ detail?: string }>(response);
      if (!response.ok) {
        throw new Error(payload?.detail || "Could not create user");
      }
      setEmail("");
      setFirstName("");
      setLastName("");
      setRole("EMPLOYEE");
      setHrCompanyName("");
      setPortalAccess("BOTH");
      setManagerId("");
      toast.success("User created");
      await loadCompanies();
      void loadUsers(search);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not create user");
    } finally {
      setSaving(false);
    }
  }

  async function addCompany() {
    if (!actorIsAdmin) {
      toast.error("Only platform admin can add companies.");
      return;
    }
    const name = newCompanyName.trim();
    if (!name) {
      toast.error("Company name is required.");
      return;
    }
    setCompanySaving(true);
    try {
      const response = await apiFetch("/org/companies/", {
        method: "POST",
        withTenant: false,
        body: JSON.stringify({
          name,
          slug: newCompanySlug.trim() || undefined,
        }),
      });
      const payload = await readJsonSafely<{ detail?: string; company?: CompanyOption }>(response);
      if (!response.ok) {
        throw new Error(payload?.detail || "Could not add company.");
      }
      toast.success(`Company added: ${payload?.company?.name || name}`);
      setNewCompanyName("");
      setNewCompanySlug("");
      await loadCompanies();
      void loadUsers(search);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not add company.");
    } finally {
      setCompanySaving(false);
    }
  }

  async function hideCompany(companyId: number) {
    if (!actorIsAdmin) {
      toast.error("Only platform admin can hide companies.");
      return;
    }
    const target = companies.find((item) => item.id === companyId);
    if (!target) return;
    if (target.slug === "default") {
      toast.error("Default Company cannot be hidden.");
      return;
    }
    setCompanySaving(true);
    try {
      const response = await apiFetch("/org/companies/", {
        method: "PATCH",
        withTenant: false,
        body: JSON.stringify({
          id: companyId,
          active: false,
        }),
      });
      const payload = await readJsonSafely<{ detail?: string }>(response);
      if (!response.ok) {
        throw new Error(payload?.detail || "Could not hide company.");
      }
      toast.success(`Removed from dropdown: ${target.name}`);
      await loadCompanies();
      void loadUsers(search);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not hide company.");
    } finally {
      setCompanySaving(false);
    }
  }

  async function patchUser(
    id: number,
    values: Partial<Pick<UserRow, "portal_access">> & { company_id?: number },
  ) {
    const response = await apiFetch(`/admin/users/${id}/`, {
      method: "PATCH",
      body: JSON.stringify(values),
    });
    if (!response.ok) {
      const payload = await readJsonSafely<{ detail?: string }>(response);
      toast.error(payload?.detail || "Update failed");
      return;
    }
    toast.success("User updated");
    void loadUsers(search);
  }

  async function removeUser(id: number) {
    const response = await apiFetch(`/admin/users/${id}/`, { method: "DELETE" });
    if (!response.ok && response.status !== 204) {
      toast.error("Delete failed");
      return;
    }
    toast.success("User deleted");
    void loadUsers(search);
  }

  async function saveUserPassword() {
    if (!passwordUser) return;
    if (!newPassword.trim()) {
      toast.error("Password is required");
      return;
    }
    if (newPassword !== confirmPassword) {
      toast.error("Password and confirm password do not match");
      return;
    }

    setPasswordSaving(true);
    try {
      const response = await apiFetch(`/admin/users/${passwordUser.id}/password/`, {
        method: "POST",
        body: JSON.stringify({
          password: newPassword,
          confirm_password: confirmPassword,
        }),
      });
      const payload = await readJsonSafely<{ detail?: string; errors?: string[] }>(response);
      if (!response.ok) {
        throw new Error(payload?.detail || payload?.errors?.join(", ") || "Could not set password");
      }
      toast.success(payload?.detail || "Password updated");
      closePasswordDialog();
      void loadUsers(search);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not set password");
    } finally {
      setPasswordSaving(false);
    }
  }

  function onCompanyChange(value: string) {
    setSelectedCompanyId(value);
    const selected = companies.find((item) => String(item.id) === value);
    if (!selected) return;
    persistSelectedOrganization({ id: selected.id, slug: selected.slug });
    void loadUsers(search);
  }

  useEffect(() => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    async function init() {
      await loadCompanies();
      await loadUsers();
      if (actorIsAdmin) {
        await loadAdminAccounts();
      }
    }
    void init();
  }, [router, actorIsAdmin]);

  if (!canManage) {
    return (
      <AppShell>
        <PageHeader
          title="Admin Users"
          description="Only HR/Admin can manage users."
          badge={<Badge variant="outline">Restricted</Badge>}
        />
        <Card className="surface-card">
          <CardHeader>
            <CardTitle>Admin Users</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">Only HR/Admin can manage users.</p>
          </CardContent>
        </Card>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <PageHeader
        title="Admin Users"
        description="Assign HR/Manager/Employee by company, set tracker access, and control login."
        badge={<Badge variant="outline">HR / Admin</Badge>}
      />

      <div className="grid gap-6">
        <Card className="surface-card">
          <CardHeader>
            <CardTitle>Company Assignment Context</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3 md:grid-cols-3">
            <div className="md:col-span-2">
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
                {selectedCompany ? `Active Company: ${selectedCompany.name}` : "No company selected"}
              </Badge>
            </div>
            {actorIsAdmin ? (
              <div className="soft-panel md:col-span-3 grid gap-3 md:grid-cols-4">
                <Input
                  placeholder="Add company name"
                  value={newCompanyName}
                  onChange={(event) => setNewCompanyName(event.target.value)}
                />
                <Input
                  placeholder="Slug (optional)"
                  value={newCompanySlug}
                  onChange={(event) => setNewCompanySlug(event.target.value)}
                />
                <Button onClick={addCompany} disabled={companySaving || !newCompanyName.trim()}>
                  {companySaving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Plus className="mr-2 h-4 w-4" />}
                  Add Company
                </Button>
                <div className="text-xs text-muted-foreground self-center">
                  Dropdown shows active companies only.
                </div>
                <div className="md:col-span-4 flex flex-wrap gap-2">
                  {companies.map((company) => (
                    <Badge key={company.id} variant="outline" className="flex items-center gap-2">
                      <span>{company.name}</span>
                      {company.slug !== "default" ? (
                        <button
                          type="button"
                          className="text-destructive"
                          onClick={() => void hideCompany(company.id)}
                          title="Remove from dropdown"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      ) : null}
                    </Badge>
                  ))}
                </div>
              </div>
            ) : null}
          </CardContent>
        </Card>

        <Card className="surface-card">
          <CardHeader>
            <CardTitle>Create User</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3 md:grid-cols-6">
            <div className="soft-panel grid gap-3 md:col-span-6 md:grid-cols-6">
              <div className="md:col-span-2">
                <Label className="mb-1 block text-xs">Assign Company</Label>
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
              {role === "HR" ? (
                <div className="md:col-span-2">
                  <Label className="mb-1 block text-xs">HR Company Name (Manual)</Label>
                  <Input
                    list="hr-company-options"
                    placeholder="Type exact company name"
                    value={hrCompanyName}
                    onChange={(event) => setHrCompanyName(event.target.value)}
                  />
                  <datalist id="hr-company-options">
                    {companies.map((company) => (
                      <option key={company.id} value={company.name} />
                    ))}
                  </datalist>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Type exact company name from added company list.
                  </p>
                </div>
              ) : null}
              <Input
                className="md:col-span-2"
                placeholder="Email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
              <Input placeholder="First Name" value={firstName} onChange={(event) => setFirstName(event.target.value)} />
              <Input placeholder="Last Name" value={lastName} onChange={(event) => setLastName(event.target.value)} />
              <Select value={role} onValueChange={setRole}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="EMPLOYEE">Employee</SelectItem>
                  <SelectItem value="MANAGER">Manager</SelectItem>
                  <SelectItem value="HR">HR</SelectItem>
                </SelectContent>
              </Select>
              <Select value={portalAccess} onValueChange={(value) => setPortalAccess(normalizePortalAccess(value))}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="MAIN">Main Leave Tracker</SelectItem>
                  <SelectItem value="ORGANIZATION">Organization Server</SelectItem>
                  <SelectItem value="BOTH">Both</SelectItem>
                </SelectContent>
              </Select>
              {role === "EMPLOYEE" ? (
                <Select
                  value={managerId || "__NONE__"}
                  onValueChange={(value) => setManagerId(value === "__NONE__" ? "" : value)}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Manager (optional)" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__NONE__">No manager</SelectItem>
                    {managers.map((manager) => (
                      <SelectItem value={String(manager.id)} key={manager.id}>
                        {manager.full_name || manager.username}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : (
                <div />
              )}
              <Button
                className="md:col-span-1"
                disabled={saving || !email || !(role === "HR" ? hrCompanyName.trim() : selectedCompanyId)}
                onClick={createUser}
              >
                {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Plus className="mr-2 h-4 w-4" />}
                Create
              </Button>
            </div>
          </CardContent>
        </Card>

        {actorIsAdmin ? (
          <Card className="surface-card">
            <CardHeader>
              <CardTitle>Admin Accounts</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-4">
              <div className="grid gap-3 md:grid-cols-4">
                <Select value={adminUserId} onValueChange={setAdminUserId}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select user" />
                  </SelectTrigger>
                  <SelectContent>
                    {users.map((item) => (
                      <SelectItem key={item.id} value={String(item.id)}>
                        {(item.full_name || item.username) + " (" + item.email + ")"}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Select value={adminLevel} onValueChange={(value) => setAdminLevel(value as "PLATFORM" | "ORGANIZATION")}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="ORGANIZATION">Organization Admin</SelectItem>
                    <SelectItem value="PLATFORM">Platform Admin</SelectItem>
                  </SelectContent>
                </Select>
                <Select
                  value={adminOrgId}
                  onValueChange={setAdminOrgId}
                  disabled={adminLevel === "PLATFORM" || loadingCompanies}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select organization" />
                  </SelectTrigger>
                  <SelectContent>
                    {companies.map((company) => (
                      <SelectItem key={company.id} value={String(company.id)}>
                        {company.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Button onClick={createAdminAccount} disabled={adminSaving}>
                  {adminSaving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Plus className="mr-2 h-4 w-4" />}
                  Save Admin
                </Button>
              </div>
              <Table className="[&_th]:h-11 [&_th]:text-xs [&_th]:uppercase [&_th]:tracking-wide">
                <TableHeader>
                  <TableRow>
                    <TableHead>User Id</TableHead>
                    <TableHead>Level</TableHead>
                    <TableHead>Organization</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {adminAccounts.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={3}>No admin accounts found.</TableCell>
                    </TableRow>
                  ) : (
                    adminAccounts.map((row) => (
                      <TableRow key={row.id}>
                        <TableCell>{row.user}</TableCell>
                        <TableCell>{row.level}</TableCell>
                        <TableCell>
                          {row.organization ? companyNameById.get(row.organization) || `Company #${row.organization}` : "Global"}
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        ) : null}

        <Card className="surface-card">
          <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <CardTitle>User Directory</CardTitle>
            <div className="flex gap-2">
              <Input
                placeholder="Search by name/email"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
              <Button variant="outline" onClick={() => loadUsers(search)}>
                Search
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            <Table className="[&_th]:h-11 [&_th]:text-xs [&_th]:uppercase [&_th]:tracking-wide">
              <TableHeader>
                <TableRow>
                  <TableHead>User</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>Company</TableHead>
                  <TableHead>Created By</TableHead>
                  <TableHead>Created In Org</TableHead>
                  <TableHead>Tracker Access</TableHead>
                  <TableHead className="text-right">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading ? (
                  <TableRow>
                    <TableCell colSpan={7}>Loading users...</TableCell>
                  </TableRow>
                ) : (
                  users.map((item) => {
                    const itemAccess = normalizePortalAccess(item.portal_access);
                    const assignedCompanyId = item.organization ? String(item.organization) : "";
                    const assignedCompanyLabel = item.organization
                      ? companyNameById.get(item.organization) || `Company #${item.organization}`
                      : "Unassigned";
                    return (
                      <TableRow key={item.id}>
                        <TableCell>
                          <p className="font-medium">{item.full_name || item.username}</p>
                          <p className="text-xs text-muted-foreground">{item.email}</p>
                        </TableCell>
                        <TableCell>
                          <Badge variant="secondary">{item.role}</Badge>
                        </TableCell>
                        <TableCell>
                          {item.role === "HR" && actorIsAdmin ? (
                            <Select
                              value={assignedCompanyId || selectedCompanyId}
                              onValueChange={(value) => patchUser(item.id, { company_id: Number(value) })}
                            >
                              <SelectTrigger className="h-8 min-w-[180px]">
                                <SelectValue placeholder="Select company" />
                              </SelectTrigger>
                              <SelectContent>
                                {companies.map((company) => (
                                  <SelectItem key={company.id} value={String(company.id)}>
                                    {company.name}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          ) : (
                            <Badge variant="outline">{assignedCompanyLabel}</Badge>
                          )}
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline">
                            {item.created_by_name || "-"}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline">
                            {item.created_in_organization_name || "-"}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <Select
                            value={itemAccess}
                            onValueChange={(value) =>
                              patchUser(item.id, { portal_access: normalizePortalAccess(value) })
                            }
                          >
                            <SelectTrigger className="h-8 min-w-[170px]">
                              <SelectValue>{portalAccessLabel(itemAccess)}</SelectValue>
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="MAIN">Main Leave Tracker</SelectItem>
                              <SelectItem value="ORGANIZATION">Organization Server</SelectItem>
                              <SelectItem value="BOTH">Both</SelectItem>
                            </SelectContent>
                          </Select>
                        </TableCell>
                        <TableCell className="text-right">
                          <div className="inline-flex items-center gap-1">
                            {canSetPassword(item) ? (
                              <Button variant="ghost" size="sm" onClick={() => openPasswordDialog(item)}>
                                <KeyRound className="mr-1 h-4 w-4" />
                                Set Password
                              </Button>
                            ) : null}
                            <Button variant="ghost" size="icon" onClick={() => removeUser(item.id)}>
                              <Trash2 className="h-4 w-4 text-destructive" />
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    );
                  })
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>

      <Dialog
        open={passwordDialogOpen}
        onOpenChange={(open) => {
          if (!open) {
            closePasswordDialog();
            return;
          }
          setPasswordDialogOpen(true);
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Set User Password</DialogTitle>
            <DialogDescription>
              {passwordUser
                ? `Set a new password for ${passwordUser.full_name || passwordUser.username}.`
                : "Set user password."}
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-3">
            <Input
              type="password"
              placeholder="New password"
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
            />
            <Input
              type="password"
              placeholder="Confirm password"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={closePasswordDialog}>
              Cancel
            </Button>
            <Button onClick={saveUserPassword} disabled={passwordSaving || !passwordUser}>
              {passwordSaving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              Save Password
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </AppShell>
  );
}
