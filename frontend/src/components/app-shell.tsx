"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  BriefcaseBusiness,
  Building2,
  ClipboardCheck,
  CalendarDays,
  LayoutDashboard,
  ListChecks,
  LogOut,
  Menu,
  Network,
  NotebookTabs,
  PlusCircle,
  ScrollText,
  ShieldCheck,
  UserCog,
  UserRound,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Sheet, SheetClose, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ThemeSelector } from "@/components/theme-selector";
import { toast } from "sonner";
import {
  clearSelectedOrganization,
  clearAuthSession,
  getAuthUser,
  getSelectedOrganizationId,
  isAdminOrHR,
  setSelectedOrganization as persistSelectedOrganization,
} from "@/lib/auth";
import { API_BASE_URL, apiFetch } from "@/lib/api";
import { cn } from "@/lib/utils";

type NavItem = {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  show: (user: ReturnType<typeof getAuthUser>) => boolean;
};

type OrganizationOption = {
  id: number;
  name: string;
  slug: string;
};

type OrganizationDirectoryPayload = {
  selected_company_id: number | null;
  results: OrganizationOption[];
};

const ORG_CACHE_KEY = "leave_tracker_org_directory_v1";
const ORG_CACHE_TTL_MS = 5 * 60 * 1000;

const navItems: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard, show: () => true },
  { href: "/leave/apply", label: "Apply Leave", icon: PlusCircle, show: () => true },
  { href: "/company-board", label: "Company Board", icon: ListChecks, show: () => true },
  { href: "/calendar", label: "Calendar", icon: CalendarDays, show: () => true },
  {
    href: "/talent",
    label: "Talent Acquisition",
    icon: BriefcaseBusiness,
    show: (user) => isAdminOrHR(user),
  },
  {
    href: "/onboarding",
    label: "Onboarding",
    icon: ClipboardCheck,
    show: (user) => isAdminOrHR(user),
  },
  {
    href: "/approvals",
    label: "Approvals",
    icon: ShieldCheck,
    show: (user) => isAdminOrHR(user),
  },
  {
    href: "/leave-policies",
    label: "Leave Policies",
    icon: NotebookTabs,
    show: (user) => isAdminOrHR(user),
  },
  {
    href: "/admin-users",
    label: "Admin Users",
    icon: UserCog,
    show: (user) => isAdminOrHR(user),
  },
  {
    href: "/audit-trail",
    label: "Audit Trail",
    icon: ScrollText,
    show: (user) => isAdminOrHR(user),
  },
  {
    href: "/architecture",
    label: "Architecture",
    icon: Network,
    show: (user) => isAdminOrHR(user),
  },
  { href: "/profile", label: "Profile", icon: UserRound, show: () => true },
];

function isActivePath(pathname: string, href: string) {
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const user = getAuthUser();
  const userId = user?.id ?? null;
  const visibleNavItems = navItems.filter((item) => item.show(user));
  const activeItem = visibleNavItems.find((item) => isActivePath(pathname, item.href));
  const [organizations, setOrganizations] = useState<OrganizationOption[]>([]);
  const [selectedOrganizationId, setSelectedOrganizationId] = useState("");
  const [loadingOrganizations, setLoadingOrganizations] = useState(false);
  const djangoBaseUrl = API_BASE_URL.replace(/\/api$/i, "");

  const handleLogout = () => {
    clearAuthSession();
    router.replace("/login");
  };

  const applyOrganizationPayload = (payload: OrganizationDirectoryPayload) => {
    const options = payload.results || [];
    setOrganizations(options);

    const storedId = getSelectedOrganizationId();
    const fallbackId = payload.selected_company_id ? String(payload.selected_company_id) : "";
    const validStored = options.some((item) => String(item.id) === storedId);
    if (storedId && !validStored) {
      clearSelectedOrganization();
    }
    const nextSelected = (validStored ? storedId : "") || fallbackId || (options[0] ? String(options[0].id) : "");
    setSelectedOrganizationId(nextSelected);

    const matched = options.find((item) => String(item.id) === nextSelected);
    if (matched) {
      persistSelectedOrganization({ id: matched.id, slug: matched.slug });
    }
  };

  useEffect(() => {
    async function loadOrganizations() {
      if (!userId) return;
      setLoadingOrganizations(true);
      const now = Date.now();
      if (typeof window !== "undefined") {
        const cachedRaw = sessionStorage.getItem(ORG_CACHE_KEY);
        if (cachedRaw) {
          try {
            const cached = JSON.parse(cachedRaw) as { ts: number; payload: OrganizationDirectoryPayload };
            if (cached?.payload?.results && now - (cached.ts || 0) < ORG_CACHE_TTL_MS) {
              applyOrganizationPayload(cached.payload);
              setLoadingOrganizations(false);
              return;
            }
          } catch {
            // Ignore malformed cache and re-fetch from server.
          }
        }
      }
      try {
        const response = await apiFetch("/org/companies/", { withTenant: false });
        if (!response.ok) {
          const payload = (await response.json().catch(() => ({}))) as { detail?: string };
          throw new Error(payload.detail || "Could not load organizations.");
        }
        const payload = (await response.json()) as OrganizationDirectoryPayload;
        applyOrganizationPayload(payload);
        if (typeof window !== "undefined") {
          sessionStorage.setItem(
            ORG_CACHE_KEY,
            JSON.stringify({
              ts: now,
              payload,
            }),
          );
        }
      } catch (error) {
        toast.error(error instanceof Error ? error.message : "Could not load organizations.");
      } finally {
        setLoadingOrganizations(false);
      }
    }

    void loadOrganizations();
  }, [userId]);

  const handleOrganizationSelect = (value: string) => {
    if (!value || value === selectedOrganizationId) {
      return;
    }
    setSelectedOrganizationId(value);
    const selected = organizations.find((item) => String(item.id) === value);
    if (!selected) return;
    persistSelectedOrganization({ id: selected.id, slug: selected.slug });
  };

  const selectedOrganization = organizations.find((item) => String(item.id) === selectedOrganizationId) || null;
  const organizationServerUrl = selectedOrganization
    ? `${djangoBaseUrl}/login/?company_name=${encodeURIComponent(selectedOrganization.name)}&next=/dashboard/`
    : `${djangoBaseUrl}/login/?next=/dashboard/`;

  const renderNav = (mobile = false, closeOnClick = false) => (
    <nav className={mobile ? "grid gap-1" : "grid gap-1 px-3"}>
      {visibleNavItems.map((item) => {
        const Icon = item.icon;
        const active = isActivePath(pathname, item.href);
        const buttonNode = (
          <Button
            asChild
            variant={active ? "default" : "ghost"}
            size={mobile ? "default" : "sm"}
            className={cn(
              "h-10 w-full justify-start gap-2 rounded-lg px-3 text-sm",
              active
                ? "shadow-[0_8px_20px_-14px_color-mix(in_oklab,var(--primary)_70%,transparent)]"
                : "text-muted-foreground hover:bg-accent/70 hover:text-foreground",
            )}
          >
            <Link href={item.href}>
              <Icon className="h-4 w-4" />
              {item.label}
            </Link>
          </Button>
        );

        if (closeOnClick) {
          return (
            <SheetClose asChild key={item.href}>
              {buttonNode}
            </SheetClose>
          );
        }

        return (
          <span key={item.href} className="contents">
            {buttonNode}
          </span>
        );
      })}
    </nav>
  );

  return (
    <div className="relative flex min-h-screen bg-background">
      <aside className="hidden w-72 shrink-0 border-r border-border/60 bg-card/45 backdrop-blur md:flex md:flex-col">
        <div className="border-b border-border/60 px-5 py-4">
          <div>
            <p className="text-base font-semibold leading-none">Leave Tracker</p>
            <p className="mt-1 text-xs text-muted-foreground">Workspace Navigation</p>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto py-3">{renderNav()}</div>
        <div className="border-t border-border/60 px-4 py-3">
          <div className="space-y-2 rounded-lg border border-border/60 bg-card/70 px-3 py-2">
            <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">Django Tenant</p>
            <Select
              value={selectedOrganizationId}
              onValueChange={handleOrganizationSelect}
              disabled={loadingOrganizations || organizations.length === 0}
            >
              <SelectTrigger className="h-9 bg-background/80 text-xs">
                <div className="flex min-w-0 items-center gap-2">
                  <Building2 className="h-3.5 w-3.5 text-muted-foreground" />
                  <SelectValue
                    placeholder={loadingOrganizations ? "Loading organizations..." : "Select organization"}
                  />
                </div>
              </SelectTrigger>
              <SelectContent>
                {organizations.map((organization) => (
                  <SelectItem key={organization.id} value={String(organization.id)}>
                    {organization.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              variant="outline"
              size="sm"
              className="h-8 w-full justify-start gap-2 text-xs"
              disabled={loadingOrganizations}
              onClick={() => {
                if (typeof window !== "undefined") {
                  window.location.href = organizationServerUrl;
                }
              }}
            >
              <Building2 className="h-3.5 w-3.5" />
              Organization Server Login
            </Button>
            <p className="truncate text-[11px] text-muted-foreground">{user?.full_name || user?.username}</p>
          </div>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-40 border-b border-border/60 bg-background/90 backdrop-blur">
          <div className="mx-auto flex w-full max-w-[1380px] items-center justify-between gap-3 px-4 py-3 md:px-6">
            <div className="flex min-w-0 items-center gap-2">
              <Sheet>
                <SheetTrigger asChild>
                  <Button variant="ghost" size="icon" className="md:hidden">
                    <Menu className="h-5 w-5" />
                  </Button>
                </SheetTrigger>
                <SheetContent side="left" className="w-[280px] p-0">
                  <div className="border-b border-border/60 px-4 py-4">
                    <p className="text-base font-semibold">Leave Tracker</p>
                    <p className="text-xs text-muted-foreground">Workspace Navigation</p>
                  </div>
                  <div className="space-y-3 p-3">
                    <ThemeSelector compact={false} />
                    {renderNav(true, true)}
                  </div>
                  <div className="mt-auto border-t border-border/60 p-3">
                    <div className="mb-2 space-y-2 rounded-lg border border-border/60 bg-card/65 px-3 py-2">
                      <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
                        Django Tenant
                      </p>
                      <Select
                        value={selectedOrganizationId}
                        onValueChange={handleOrganizationSelect}
                        disabled={loadingOrganizations || organizations.length === 0}
                      >
                        <SelectTrigger className="h-9 bg-background/80 text-xs">
                          <div className="flex min-w-0 items-center gap-2">
                            <Building2 className="h-3.5 w-3.5 text-muted-foreground" />
                            <SelectValue
                              placeholder={loadingOrganizations ? "Loading organizations..." : "Select organization"}
                            />
                          </div>
                        </SelectTrigger>
                        <SelectContent>
                          {organizations.map((organization) => (
                            <SelectItem key={organization.id} value={String(organization.id)}>
                              {organization.name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-8 w-full justify-start gap-2 text-xs"
                        disabled={loadingOrganizations}
                        onClick={() => {
                          if (typeof window !== "undefined") {
                            window.location.href = organizationServerUrl;
                          }
                        }}
                      >
                        <Building2 className="h-3.5 w-3.5" />
                        Organization Server Login
                      </Button>
                      <p className="text-xs text-muted-foreground">{user?.full_name || user?.username}</p>
                    </div>
                    <SheetClose asChild>
                      <Button variant="outline" className="w-full gap-2" onClick={handleLogout}>
                        <LogOut className="h-4 w-4" />
                        Logout
                      </Button>
                    </SheetClose>
                  </div>
                </SheetContent>
              </Sheet>
              <div className="min-w-0">
                <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">Workspace</p>
                <h1 className="truncate text-sm font-semibold md:text-base">{activeItem?.label || "Leave Tracker"}</h1>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <ThemeSelector compact className="hidden sm:flex" />
              <span className="hidden max-w-[180px] truncate rounded-md border border-border/60 bg-card/70 px-2.5 py-1 text-xs text-muted-foreground sm:inline">
                {user?.full_name || user?.username}
              </span>
              <Button variant="outline" size="sm" className="gap-2 border-border/70 bg-card/75" onClick={handleLogout}>
                <LogOut className="h-4 w-4" />
                Logout
              </Button>
            </div>
          </div>
        </header>

        <main className="px-4 py-6 md:px-6">
          <div className="page-wrap">{children}</div>
        </main>
      </div>
    </div>
  );
}
