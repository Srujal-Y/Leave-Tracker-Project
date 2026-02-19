import {
  clearSelectedOrganization,
  clearAuthSession,
  getAccessToken,
  getRefreshToken,
  getSelectedOrganizationId,
  getSelectedOrganizationSlug,
  setAuthSession,
  type AuthUser,
} from "@/lib/auth";

const rawApiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000/api";
const API_BASE_URL = rawApiBaseUrl.trim().replace(/\/+$/, "");

export async function readJsonSafely<T>(response: Response): Promise<T | null> {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text) as T;
  } catch {
    return null;
  }
}

type ApiFetchInit = RequestInit & {
  withTenant?: boolean;
  timeoutMs?: number;
};

function isAuthUser(value: unknown): value is AuthUser {
  if (!value || typeof value !== "object") return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.id === "number" &&
    typeof v.username === "string" &&
    typeof v.email === "string" &&
    typeof v.full_name === "string" &&
    typeof v.role === "string"
  );
}

async function refreshAccessToken() {
  const refresh = getRefreshToken();
  if (!refresh) return "";
  const response = await fetch(`${API_BASE_URL}/auth/refresh/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh }),
  });
  if (!response.ok) {
    clearAuthSession();
    return "";
  }
  const payload = (await readJsonSafely<{ access?: string }>(response)) || {};
  const nextAccess = payload.access || "";
  if (!nextAccess) {
    clearAuthSession();
    return "";
  }
  const userResponse = await fetch(`${API_BASE_URL}/auth/me/`, {
    headers: { Authorization: `Bearer ${nextAccess}` },
  });
  if (!userResponse.ok) {
    clearAuthSession();
    return "";
  }
  const user = await readJsonSafely(userResponse);
  if (!isAuthUser(user)) {
    clearAuthSession();
    return "";
  }
  setAuthSession(nextAccess, refresh, user);
  return nextAccess;
}

export async function apiFetch(path: string, init: ApiFetchInit = {}, retry = true) {
  const withTenant = init.withTenant !== false;
  const timeoutMs = typeof init.timeoutMs === "number" && init.timeoutMs > 0 ? init.timeoutMs : 20000;
  const requestInit: RequestInit = { ...init };
  delete (requestInit as ApiFetchInit).withTenant;
  delete (requestInit as ApiFetchInit).timeoutMs;
  const headers = new Headers(init.headers || {});
  const token = getAccessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (withTenant) {
    const companyId = getSelectedOrganizationId();
    const schema = getSelectedOrganizationSlug();
    if (companyId) headers.set("X-Company-Id", companyId);
    if (schema) headers.set("X-DTS-SCHEMA", schema);
  }
  if (!headers.has("Content-Type") && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...requestInit,
      headers,
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timeout);
  }

  if (withTenant && (response.status === 400 || response.status === 403)) {
    const payload = await readJsonSafely<{ detail?: string }>(response.clone());
    const detail = (payload?.detail || "").toLowerCase();
    if (detail.includes("tenant") || detail.includes("organization") || detail.includes("schema")) {
      clearSelectedOrganization();
    }
  }

  if (response.status === 401 && retry) {
    const nextAccess = await refreshAccessToken();
    if (nextAccess) {
      return apiFetch(path, init, false);
    }
  }
  return response;
}

export { API_BASE_URL };

