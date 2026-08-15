const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("token");
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

// Campaigns
export const campaigns = {
  types: () => request<CampaignType[]>("/api/campaigns/types"),
  list: () => request<Campaign[]>("/api/campaigns"),
  get: (id: string) => request<Campaign>(`/api/campaigns/${id}`),
  create: (data: Partial<Campaign>) =>
    request<Campaign>("/api/campaigns", { method: "POST", body: JSON.stringify(data) }),
  update: (id: string, data: Partial<Campaign>) =>
    request<Campaign>(`/api/campaigns/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  remove: (id: string) => request<void>(`/api/campaigns/${id}`, { method: "DELETE" }),
  run: (id: string, opts?: { company?: string; max_contacts?: number }) =>
    request<{ ok: boolean; run_id: string; balance: number }>(`/api/campaigns/${id}/run`, {
      method: "POST",
      body: JSON.stringify(opts ?? {}),
    }),
  contacts: (id: string) => request<Contact[]>(`/api/campaigns/${id}/contacts`),
  runs: (id: string) => request<AgentRun[]>(`/api/campaigns/${id}/runs`),
};

// Contacts
export const contacts = {
  list: (params?: { campaign_id?: string; company?: string; status?: string }) => {
    const q = new URLSearchParams();
    if (params?.campaign_id) q.set("campaign_id", params.campaign_id);
    if (params?.company) q.set("company", params.company);
    if (params?.status) q.set("status", params.status);
    return request<Contact[]>(`/api/contacts?${q}`);
  },
  get: (id: string) => request<Contact>(`/api/contacts/${id}`),
  update: (id: string, data: Partial<Contact>) =>
    request<Contact>(`/api/contacts/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  delete: (id: string) => request<void>(`/api/contacts/${id}`, { method: "DELETE" }),
  deleteAll: (campaignId?: string) =>
    request<void>(`/api/contacts${campaignId ? `?campaign_id=${campaignId}` : ""}`, {
      method: "DELETE",
    }),
  draftMessage: (id: string) =>
    request<Contact>(`/api/contacts/${id}/draft-message`, { method: "POST" }),
};

// Profile (background used to personalize outreach)
export const profile = {
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
  autocompleteCompanies: (seedCompanies: string[]) =>
    request<{ suggestions: string[] }>("/api/settings/companies/autocomplete", {
      method: "POST",
      body: JSON.stringify({ seed_companies: seedCompanies }),
    }),
};

// Agent runs
export const agents = {
  runs: () => request<AgentRun[]>("/api/agents/runs"),
};

// Billing — prepaid credits
export const billing = {
  packs: () => request<CreditPack[]>("/api/billing/packs"),
  balance: () => request<CreditBalance>("/api/billing/balance"),
  ledger: () => request<LedgerEntry[]>("/api/billing/ledger"),
  checkout: (packId: string) =>
    request<{ url: string; session_id: string }>("/api/billing/checkout", {
      method: "POST",
      body: JSON.stringify({ pack_id: packId }),
    }),
};

// MCP connections
export const connections = {
  list: () => request<Connection[]>("/oauth/connections"),
  revoke: (id: string) => request<void>(`/oauth/connections/${id}`, { method: "DELETE" }),
  consent: (data: ConsentPayload) =>
    request<{ redirect_url: string }>("/oauth/consent", {
      method: "POST",
      body: JSON.stringify(data),
    }),
};

// Types
export interface DashboardStats {
  contacts_count: number;
  drafted_count: number;
  in_flight_count: number;
  campaign_count: number;
  active_campaign_count: number;
  credits: {
    balance: number;
    spent_this_week: number;
    low_balance: boolean;
  };
  setup: {
    profile_completed: boolean;
    resume_uploaded: boolean;
    campaign_created: boolean;
    first_run_completed: boolean;
  };
}

export interface ActivityItem {
  id: string;
  campaign_id: string | null;
  trigger: string;
  contacts_found: number;
  drafts_written: number;
  credits_spent: number;
  summary: string | null;
  timestamp: string | null;
}

export type CampaignTypeKey =
  | "business_development"
  | "job_search"
  | "fundraising"
  | "recruiting"
  | "custom";

export interface CampaignType {
  key: CampaignTypeKey;
  label: string;
  description: string;
  example_titles: string[];
}

export interface Campaign {
  id: string;
  name: string;
  campaign_type: CampaignTypeKey;
  objective: string | null;
  target_titles: string[];
  target_companies: string[];
  target_industries: string[];
  target_locations: string[];
  excluded_companies: string[];
  company_stages: string[];
  status: "draft" | "active" | "paused";
  autopilot_enabled: boolean;
  autopilot_cadence_days: number;
  weekly_credit_cap: number;
  contact_count: number;
  credits_spent_this_week: number;
  created_at: string | null;
  last_run_at: string | null;
}

export interface Contact {
  id: string;
  campaign_id: string | null;
  company: string;
  first_name: string | null;
  last_name: string | null;
  title: string | null;
  linkedin_url: string | null;
  email: string | null;
  seniority: string | null;
  department: string | null;
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
    summary?: string;
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
  headline: string | null;
  value_prop: string | null;
  timezone: string | null;
  email_digest_enabled: boolean;
  email_low_balance_enabled: boolean;
}

export interface AgentRun {
  id: string;
  campaign_id?: string | null;
  agent_type?: string;
  trigger: string;
  status: string;
  contacts_found: number;
  drafts_written: number;
  credits_spent: number;
  tokens_used?: number | null;
  duration_ms?: number | null;
  error_message: string | null;
  current_step: string | null;
  output_summary?: string | null;
  started_at: string;
  completed_at: string | null;
}

export interface CreditPack {
  id: string;
  name: string;
  credits: number;
  amount_cents: number;
  price_per_credit_cents: number;
}

export interface CreditBalance {
  balance: number;
  low_balance: boolean;
  costs: { contact: number; draft: number; mcp_call: number };
}

export interface LedgerEntry {
  id: string;
  delta: number;
  reason: string;
  campaign_id: string | null;
  created_at: string | null;
}

export interface Connection {
  id: string;
  client_id: string;
  client_name: string;
  scope: string[];
  created_at: string | null;
  last_used_at: string | null;
  expires_at: string | null;
}

export interface ConsentPayload {
  client_id: string;
  redirect_uri: string;
  scope: string;
  state?: string;
  code_challenge: string;
  code_challenge_method: string;
  resource?: string;
  approved: boolean;
}
