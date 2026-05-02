const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("token");
}

async function downloadBlob(path: string, filename: string): Promise<void> {
  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, { headers });
  if (res.status === 401) { localStorage.removeItem("token"); window.location.href = "/login"; throw new Error("Unauthorized"); }
  if (!res.ok) { const err = await res.json().catch(() => ({ detail: res.statusText })); throw new Error(err.detail || "Download failed"); }

  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });

  if (res.status === 401) {
    localStorage.removeItem("token");
    window.location.href = "/login";
    throw new Error("Unauthorized");
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Request failed");
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

// Auth
export const auth = {
  register: (email: string, password: string, full_name?: string) =>
    request<{ access_token: string }>("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, full_name }),
    }),
  login: (email: string, password: string) =>
    request<{ access_token: string }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  me: () => request<{ id: string; email: string; full_name: string | null }>("/api/auth/me"),
  logout: () => request<{ ok: boolean }>("/api/auth/logout", { method: "POST" }),
};

// Dashboard
export const dashboard = {
  stats: () => request<DashboardStats>("/api/dashboard/stats"),
  activity: () => request<ActivityItem[]>("/api/dashboard/activity"),
};

// Jobs
export const jobs = {
  list: (params?: { score_min?: number; is_new?: boolean; page?: number }) => {
    const q = new URLSearchParams();
    if (params?.score_min) q.set("score_min", String(params.score_min));
    if (params?.is_new !== undefined) q.set("is_new", String(params.is_new));
    if (params?.page) q.set("page", String(params.page));
    return request<Job[]>(`/api/jobs?${q}`);
  },
  get: (id: string) => request<Job>(`/api/jobs/${id}`),
  dismiss: (id: string) => request(`/api/jobs/${id}/dismiss`, { method: "PATCH" }),
};

// Applications
export const applications = {
  list: (status?: string) => {
    const q = status ? `?status=${status}` : "";
    return request<ApplicationDraft[]>(`/api/applications${q}`);
  },
  get: (id: string) => request<ApplicationDraft>(`/api/applications/${id}`),
  generate: (jobId: string) =>
    request<ApplicationDraft>(`/api/applications/generate/${jobId}`, { method: "POST" }),
  downloadPdf: (id: string, filename: string) =>
    downloadBlob(`/api/applications/${id}/pdf`, filename),
  updateCoverLetter: (id: string, cover_letter: string) =>
    request(`/api/applications/${id}/cover-letter`, {
      method: "PATCH",
      body: JSON.stringify({ cover_letter }),
    }),
};

// Contacts
export const contacts = {
  list: (params?: { company?: string; status?: string }) => {
    const q = new URLSearchParams();
    if (params?.company) q.set("company", params.company);
    if (params?.status) q.set("status", params.status);
    return request<Contact[]>(`/api/contacts?${q}`);
  },
  get: (id: string) => request<Contact>(`/api/contacts/${id}`),
  update: (id: string, data: Partial<Contact>) =>
    request<Contact>(`/api/contacts/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  delete: (id: string) => request<void>(`/api/contacts/${id}`, { method: "DELETE" }),
  deleteAll: () => request<void>("/api/contacts", { method: "DELETE" }),
  draftMessage: (id: string) =>
    request<Contact>(`/api/contacts/${id}/draft-message`, { method: "POST" }),
};

// Resume
export const resume = {
  delete: (id: string) => request<void>(`/api/resume/${id}`, { method: "DELETE" }),
  upload: (file: File) => {
    const token = getToken();
    const fd = new FormData();
    fd.append("file", file);
    return fetch(`${API_BASE}/api/resume/upload`, {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: fd,
    }).then(async (r) => {
      if (!r.ok) throw new Error((await r.json()).detail || "Upload failed");
      return r.json() as Promise<ResumeData>;
    });
  },
  active: () => request<ResumeData>("/api/resume/active"),
};

// Settings
export const settingsApi = {
  get: () => request<Preferences>("/api/settings"),
  update: (data: Partial<Preferences>) =>
    request<Preferences>("/api/settings", { method: "PUT", body: JSON.stringify(data) }),
};

// Agents
export const agents = {
  runJobScout: () => request("/api/agents/job-scout/run", { method: "POST" }),
  runNetworking: () => request("/api/agents/networking/run", { method: "POST" }),
  runNetworkingForCompany: (company: string) =>
    request("/api/agents/networking/run-single", { method: "POST", body: JSON.stringify({ company }) }),
  runs: () => request<AgentRun[]>("/api/agents/runs"),
};

// Stripe
export const stripe = {
  createCheckout: () =>
    request<{ url: string }>("/api/stripe/create-checkout-session", { method: "POST" }),
  cancelSubscription: () =>
    request<{ ok: boolean }>("/api/stripe/cancel-subscription", { method: "POST" }),
};

// Types
export interface DashboardStats {
  jobs_count: number;
  new_jobs_count: number;
  applications_count: number;
  contacts_count: number;
  plan: "free" | "pro";
  target_roles_configured: boolean;
  usage: {
    jobs_surfaced: number;
    contacts_surfaced: number;
    jobs_limit: number | null;
    contacts_limit: number | null;
    agent_runs: { job_scout: number; networking: number; application: number };
    agent_runs_limit: number | null;
  };
}

export interface ActivityItem {
  type: "jobs_found" | "contacts_found" | "drafts_created";
  count: number;
  timestamp: string;
}

export interface Job {
  id: string;
  title: string;
  company: string;
  location: string | null;
  description: string | null;
  url: string;
  salary_min: number | null;
  salary_max: number | null;
  employment_type: string | null;
  match_score: number | null;
  match_reasoning: string | null;
  is_new: boolean;
  is_dismissed: boolean;
  discovered_at: string;
  source: string;
  application_id: string | null;
}

export interface ApplicationDraft {
  id: string;
  status: string;
  tailored_resume: Record<string, unknown> | null;
  cover_letter: string | null;
  tailoring_notes: string | null;
  created_at: string;
  job: {
    id: string;
    title: string;
    company: string;
    location: string | null;
    url: string;
    match_score: number | null;
    description: string | null;
  } | null;
}

export interface Contact {
  id: string;
  company: string;
  first_name: string | null;
  last_name: string | null;
  title: string | null;
  linkedin_url: string | null;
  email: string | null;
  seniority: string | null;
  relevance_score: number | null;
  relevance_reasoning: string | null;
  outreach_status: string;
  outreach_message: string | null;
  notes: string | null;
  discovered_at: string;
}

export interface ResumeData {
  id: string;
  filename: string;
  file_type: string;
  structured_data: {
    name?: string;
    email?: string;
    skills?: string[];
    experience?: Array<{
      company: string;
      role: string;
      start?: string;
      end?: string;
      bullets: string[];
    }>;
    education?: Array<{ institution: string; degree: string; year?: string }>;
  } | null;
  parsed_at: string | null;
}

export interface Preferences {
  target_roles: string[];
  target_companies: string[];
  target_locations: string[];
  excluded_companies: string[];
  min_salary: number | null;
  max_salary: number | null;
  employment_types: string[];
  experience_level: string | null;
  salary_type: "hourly" | "salary" | null;
  location_flexible: boolean;
  work_environment: string[];
  open_to_similar_companies: boolean;
  company_stages: string[];
  company_industries: string[];
  scout_enabled: boolean;
  networking_enabled: boolean;
}

export interface AgentRun {
  id: string;
  agent_type: string;
  trigger: string;
  status: string;
  jobs_found: number;
  contacts_found: number;
  applications_created: number;
  tokens_used: number | null;
  duration_ms: number | null;
  error_message: string | null;
  started_at: string;
  completed_at: string | null;
}
