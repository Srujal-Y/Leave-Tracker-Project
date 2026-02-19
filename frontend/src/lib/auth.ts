export type AuthUser = {
  id: number;
  username: string;
  email: string;
  full_name: string;
  role: "EMPLOYEE" | "MANAGER" | "HR" | string;
  organization?: number | null;
  organization_slug?: string;
  is_admin?: boolean;
  portal_access?: "MAIN" | "ORGANIZATION" | "BOTH" | string;
};

const ACCESS_KEY = "leave_tracker_access";
const REFRESH_KEY = "leave_tracker_refresh";
const USER_KEY = "leave_tracker_user";
const ORG_ID_KEY = "leave_tracker_org_id";
const ORG_SLUG_KEY = "leave_tracker_org_slug";

function isClient() {
  return typeof window !== "undefined";
}

export function getAccessToken() {
  if (!isClient()) return "";
  return localStorage.getItem(ACCESS_KEY) || "";
}

export function getRefreshToken() {
  if (!isClient()) return "";
  return localStorage.getItem(REFRESH_KEY) || "";
}

export function setAuthSession(access: string, refresh: string, user: AuthUser) {
  if (!isClient()) return;
  localStorage.setItem(ACCESS_KEY, access);
  localStorage.setItem(REFRESH_KEY, refresh);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
  localStorage.removeItem(ORG_ID_KEY);
  localStorage.removeItem(ORG_SLUG_KEY);
  if (user.organization) {
    localStorage.setItem(ORG_ID_KEY, String(user.organization));
  }
  if (user.organization_slug) {
    localStorage.setItem(ORG_SLUG_KEY, user.organization_slug);
  }
}

export function clearAuthSession() {
  if (!isClient()) return;
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
  localStorage.removeItem(USER_KEY);
  localStorage.removeItem(ORG_ID_KEY);
  localStorage.removeItem(ORG_SLUG_KEY);
}

export function getAuthUser(): AuthUser | null {
  if (!isClient()) return null;
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthUser;
  } catch {
    return null;
  }
}

export function isAdmin(user: AuthUser | null) {
  return Boolean(user?.is_admin);
}

export function isAdminOrHR(user: AuthUser | null) {
  return Boolean(isAdmin(user) || user?.role === "HR");
}

export function getSelectedOrganizationId() {
  if (!isClient()) return "";
  return localStorage.getItem(ORG_ID_KEY) || "";
}

export function getSelectedOrganizationSlug() {
  if (!isClient()) return "";
  return localStorage.getItem(ORG_SLUG_KEY) || "";
}

export function setSelectedOrganization(organization: { id: number; slug: string }) {
  if (!isClient()) return;
  localStorage.setItem(ORG_ID_KEY, String(organization.id));
  localStorage.setItem(ORG_SLUG_KEY, organization.slug);
}

export function clearSelectedOrganization() {
  if (!isClient()) return;
  localStorage.removeItem(ORG_ID_KEY);
  localStorage.removeItem(ORG_SLUG_KEY);
}
