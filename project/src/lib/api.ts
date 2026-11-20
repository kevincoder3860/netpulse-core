import axios, { AxiosError, type AxiosInstance } from 'axios';
import type {
  HotspotPlan, Nas, StaffMember, StaffRole, Tenant, Transaction,
  Customer, ActiveSession, Invoice, SupportTicket, TicketMessage,
  SystemUser, PlatformSettings
} from '@/lib/types';
import { jwtDecode } from 'jwt-decode';
import { API_BASE_URL, API_FALLBACK_ROOT, API_TOKEN_ROOT } from '@/lib/config';

const API_ROOT = API_BASE_URL;
const TOKEN_ROOT = API_TOKEN_ROOT;

export interface PortalConfig {
  business_name: string;
  headline: string;
  logo_url: string;
  brand_color: string;
  terms_of_service: string;
  plans: HotspotPlan[];
}

export interface VendorDashboardData {
  daily_revenue: number;
  net_earnings: number;
  active_routers: number;
  total_routers: number;
  recent_transactions: Transaction[];
}

export interface PaymentStartResponse {
  message: string;
  reference: string;
  checkout_request_id: string;
  amount: number;
  amount_cents: number;
}

export interface TransactionStatusResponse {
  checkout_request_id: string;
  status: Transaction['status'];
  updated_at?: string;
  hotspot_username?: string | null;
  hotspot_password?: string | null;
}

export interface RouterMetrics {
  router_id: string;
  ip_address: string;
  cpu_usage_percent: number;
  memory_used_bytes: number;
  memory_free_bytes: number;
  memory_total_bytes: number;
  memory_usage_percent: number;
  uptime: string;
  interfaces: { name: string; rx_bytes: number; tx_bytes: number }[];
  active_hotspot_users: number;
  captured_at: string;
}

export interface AnalyticsData {
  income_today: number;
  income_month: number;
  active_users: number;
  total_users: number;
  hotspot_status: { active: number; inactive: number; total: number };
  health: { server_cpu: number; mikrotik_cpu: number; memory: number; disk: number; router_memory: number };
  traffic: { timestamp: string; tx_bytes: number; rx_bytes: number }[];
  top_downloaders: { mac_address: string; upload: number; download: number }[];
  activity_calendar: { activity_date: string; users: number }[];
}

export interface TelemetryHealth {
  income_today?: number;
  income_month?: number;
  active_users?: number;
  total_users?: number;
  hotspot_status: { active: number; inactive: number; total: number };
  health: { server_cpu: number; mikrotik_cpu: number; memory: number; disk: number; router_memory: number };
  traffic: { timestamp: string; tx_kbps: number; rx_kbps: number };
  top_downloaders?: { mac_address: string; upload: number; download: number }[];
  activity_calendar?: { activity_date: string; users: number }[];
  live_telemetry?: { rx_bytes: number; tx_bytes: number; interface: string };
  router_stats?: { total_routers: number; online_routers: number; offline_routers: number };
}

export interface VoucherRecord { id: number; code: string; status: string; assigned_mac: string; created_at: string; expires_at: string | null; plan: number | null; router: number | null; }
export interface RechargeRecord { id: number; username: string; mac_address: string; plan_name: string; router_name: string; method: string; expires_at: string | null; status: string; }

const accessToken = () => localStorage.getItem('np_access');
const refreshToken = () => localStorage.getItem('np_refresh');

export interface AuthClaims { role: 'SUPERADMIN' | 'VENDOR' | 'STAFF' | 'CUSTOMER' | 'SUPPORT_AGENT' | 'BILLING_ADMIN' | null; staff_role?: 'MANAGER' | 'TECHNICIAN' | 'CASHIER' | null; tenant_id: string | null; email: string; is_superadmin?: boolean; }

export function getAuthClaims(): AuthClaims | null {
  const token = accessToken();
  if (!token) return null;
  try { return jwtDecode<AuthClaims>(token); } catch { return null; }
}

function clearSession() {
  localStorage.removeItem('np_access');
  localStorage.removeItem('np_refresh');
  window.dispatchEvent(new Event('np:session-expired'));
}

export const http: AxiosInstance = axios.create({
  baseURL: API_ROOT,
  headers: { 'Content-Type': 'application/json' },
});

let refreshPromise: Promise<string | null> | null = null;

http.interceptors.request.use((config) => {
  const token = accessToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

http.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config;
    if (!error.response && original && API_FALLBACK_ROOT && original.baseURL !== API_FALLBACK_ROOT) {
      return http({ ...original, baseURL: API_FALLBACK_ROOT });
    }
    if (error.response?.status !== 401 || !original || original.url?.includes('/refresh/')) throw error;
    const refresh = refreshToken();
    if (!refresh) { clearSession(); throw error; }
    refreshPromise ||= axios.post<{ access: string }>(`${TOKEN_ROOT}/refresh/`, { refresh })
      .then(({ data }) => { localStorage.setItem('np_access', data.access); return data.access; })
      .catch(() => null)
      .finally(() => { refreshPromise = null; });
    const token = await refreshPromise;
    if (!token) { clearSession(); throw error; }
    original.headers.Authorization = `Bearer ${token}`;
    return http(original);
  },
);

function unwrap<T>(request: Promise<{ data: T }>) {
  return request.then(({ data }) => data);
}

function apiErrorMessage(error: unknown, fallback: string) {
  if (!axios.isAxiosError(error)) return error instanceof Error ? error.message : fallback;
  const formatResponseData = (value: unknown): string => {
    if (typeof value === 'string') return value;
    if (typeof value === 'number' || typeof value === 'boolean') return String(value);
    if (Array.isArray(value)) {
      return value.map((item) => formatResponseData(item)).filter(Boolean).join(', ');
    }
    if (!value || typeof value !== 'object') return '';

    return Object.entries(value as Record<string, unknown>)
      .map(([key, item]) => {
        const message = formatResponseData(item);
        if (!message) return '';
        return key === 'detail' || key === 'message' || key === 'non_field_errors'
          ? message
          : `${key}: ${message}`;
      })
      .filter(Boolean)
      .join('; ');
  };

  const detail = formatResponseData(error.response?.data);
  return detail || (error.response ? fallback : error.message || fallback);
}

export const api = {
  async signIn(identifier: string, password: string) {
    try {
      const postLogin = (root: string) => axios.post<{ access: string; refresh: string }>(`${root}/login/`, { username: identifier, password });
      let data: { access: string; refresh: string };
      try {
        ({ data } = await postLogin(TOKEN_ROOT));
      } catch (error) {
        if (!axios.isAxiosError(error) || error.response || !API_FALLBACK_ROOT) throw error;
        ({ data } = await postLogin(`${API_FALLBACK_ROOT}/auth`));
      }
      localStorage.setItem('np_access', data.access);
      localStorage.setItem('np_refresh', data.refresh);
      return data;
    } catch (error) {
      if (!axios.isAxiosError(error)) throw error;
      if (error.response?.status === 401) {
        const detail = apiErrorMessage(error, '');
        throw new Error(detail
          ? `Invalid email/username or password. ${detail}`
          : 'Invalid email/username or password.');
      }
      if (error.response) {
        const detail = apiErrorMessage(error, 'The server did not provide additional error details.');
        throw new Error(`Sign-in failed (HTTP ${error.response.status}): ${detail}`);
      }
      if (error.code === 'ECONNABORTED' || error.code === 'ETIMEDOUT') {
        throw new Error(`The sign-in request to ${API_BASE_URL} timed out. Please try again.`);
      }
      if (error.code === 'ERR_NETWORK') {
        throw new Error(`Could not connect to the API at ${API_BASE_URL}. Check your network connection and try again.`);
      }
      throw new Error(error.message || 'Unable to sign in.');
    }
  },
  register: async (payload: {
    email: string;
    password: string;
    business_name?: string;
    company_name?: string;
    first_name?: string;
    last_name?: string;
    phone_number: string;
  }) => {
    try {
      const { data } = await axios.post<{ access: string; refresh: string }>(`${API_ROOT}/auth/register/vendor/`, payload, { headers: { 'Content-Type': 'application/json' } });
      localStorage.setItem('np_access', data.access);
      localStorage.setItem('np_refresh', data.refresh);
      return data;
    } catch (error) {
      if (!axios.isAxiosError(error)) throw error;
      if (error.response) {
        const detail = apiErrorMessage(error, 'The server did not provide additional error details.');
        throw new Error(`Registration failed (HTTP ${error.response.status}): ${detail}`);
      }

      if (error.code === 'ECONNABORTED' || error.code === 'ETIMEDOUT') {
        throw new Error(`The registration request to ${API_BASE_URL} timed out. Please try again.`);
      }
      if (error.code === 'ERR_NETWORK') {
        throw new Error(`Could not connect to the API at ${API_BASE_URL}. Check your network connection and try again.`);
      }
      throw new Error(error.message || 'Unable to create the vendor account.');
    }
  },
  signOut() { localStorage.removeItem('np_access'); localStorage.removeItem('np_refresh'); },
  isAuthenticated() { return Boolean(accessToken()); },
  getAuthClaims,
  getTenants: () => unwrap<Tenant[]>(http.get('/tenants/')),
  createTenant: (payload: Partial<Tenant>) => unwrap<Tenant>(http.post('/tenants/', payload)),
  updateTenant: (id: string, payload: Partial<Tenant> & { paystack_secret_key?: string }) => unwrap<Tenant>(http.patch(`/tenants/${id}/`, payload)),
  getRouters: (tenantId?: string) => unwrap<Nas[]>(http.get('/routers/', { params: tenantId ? { tenant_id: tenantId } : undefined })),
  createRouter: async (payload: {
    tenant: string;
    nasname: string;
    shortname: string;
    nas_ip?: string;
    mac_address?: string;
    secret: string;
    api_port?: number;
    api_username?: string;
    api_password?: string;
    radius_server_ip?: string;
    shared_secret?: string;
    type?: string;
  }) => {
    try {
      const { data } = await http.post<Nas>('/routers/', payload);
      return data;
    } catch (error) {
      throw new Error(apiErrorMessage(error, 'Unable to create router.'));
    }
  },
  updateRouter: async (id: string, payload: Record<string, string | number>) => {
    try {
      const { data } = await http.patch<Nas>(`/routers/${id}/`, payload);
      return data;
    } catch (error) {
      throw new Error(apiErrorMessage(error, 'Unable to update router.'));
    }
  },
  deleteRouter: async (id: string) => {
    try {
      await http.delete(`/routers/${id}/`);
    } catch (error) {
      throw new Error(apiErrorMessage(error, 'Unable to delete router.'));
    }
  },
  getRouterScript: (id: string) => unwrap<{ script: string }>(http.get(`/routers/${id}/config_script/`)),
  getRouterMetrics: (id: string) => unwrap<RouterMetrics>(http.get(`/routers/${id}/metrics/`)),
  provisionRouter: async (id: string, payload: Record<string, string | number>) => {
    try {
      const { data } = await http.post<{ ok: boolean; success: boolean; code: string; message: string; radius?: Record<string, unknown>; commands?: Array<Record<string, unknown>> }>(`/routers/${id}/provision/`, payload);
      return data;
    } catch (error) {
      throw new Error(apiErrorMessage(error, 'Unable to provision router.'));
    }
  },
  getPlans: (tenantId: string, activeOnly = false) => unwrap<HotspotPlan[]>(http.get('/plans/', { params: { tenant_id: tenantId, ...(activeOnly ? { is_active: true } : {}) } })),
  createPlan: (payload: Partial<HotspotPlan> & { tenant: string }) => unwrap<HotspotPlan>(http.post('/plans/', payload)),
  updatePlan: (id: string, payload: Partial<HotspotPlan>) => unwrap<HotspotPlan>(http.patch(`/plans/${id}/`, payload)),
  getTransactions: (tenantId?: string) => unwrap<Transaction[]>(http.get('/transactions/', { params: tenantId ? { tenant_id: tenantId } : undefined })),
  getVendorDashboard: (tenantId: string) => unwrap<VendorDashboardData>(http.get('/vendors/dashboard/', { params: { tenant_id: tenantId } })),
  getSuperAdminMetrics: () => unwrap<Record<string, number>>(http.get('/superadmin/metrics/')),
  updateTenantStatus: (tenantId: string, action: 'suspend' | 'close', reason: string) => unwrap<Tenant>(http.post(`/superadmin/tenants/${tenantId}/${action}/`, { reason })),
  impersonateTenant: (tenantId: string) => unwrap<{ access: string; tenant_id: string; read_only: boolean }>(http.post(`/superadmin/tenants/${tenantId}/impersonate/`)),
  getStaff: () => unwrap<StaffMember[]>(http.get('/vendors/staff/')),
  inviteStaff: (payload: { email: string; password: string; role: StaffRole }) => unwrap<StaffMember>(http.post('/vendors/staff/', payload)),
  updateStaff: (id: number, payload: Partial<Pick<StaffMember, 'role' | 'is_active'>>) => unwrap<StaffMember>(http.patch(`/vendors/staff/${id}/`, payload)),
  getPortalConfig: (nasId: string) => unwrap<PortalConfig>(http.get(`/portal/${nasId}/`)),
  initiatePaystackMobileMoney: async (data: {
    tenant_id: string;
    plan_id: string | number;
    phone_number: string;
    nas_id?: string | number;
    mac_address?: string;
  }) => {
    try {
      return await unwrap<PaymentStartResponse>(http.post('/billing/paystack/stk-push/', data));
    } catch (error) {
      throw new Error(apiErrorMessage(error, 'Unable to start the Paystack M-Pesa payment.'));
    }
  },
  getTransactionStatus: (checkoutRequestId: string) => unwrap<TransactionStatusResponse>(http.get(`/transactions/${checkoutRequestId}/status/`)),
  getAnalytics: (tenantId?: string) => unwrap<AnalyticsData>(http.get('/analytics/dashboard/', { params: tenantId ? { tenant_id: tenantId } : undefined })),
  getVouchers: (tenantId?: string) => unwrap<VoucherRecord[]>(http.get('/vouchers/', { params: tenantId ? { tenant_id: tenantId } : undefined })),
  generateVouchers: (payload: { tenant: string; plan?: number; router?: number; count: number; valid_days: number }) => unwrap<VoucherRecord[]>(http.post('/vouchers/', payload)),
  deleteUsedVouchers: () => unwrap<{ deleted: number }>(http.delete('/vouchers/delete-used/')),
  getRecharges: (tenantId?: string) => unwrap<RechargeRecord[]>(http.get('/recharges/', { params: tenantId ? { tenant_id: tenantId } : undefined })),
  getBurstProfiles: (tenantId?: string) => unwrap<Record<string, unknown>[]>(http.get('/burst-profiles/', { params: tenantId ? { tenant_id: tenantId } : undefined })),
  getFupProfiles: (tenantId?: string) => unwrap<Record<string, unknown>[]>(http.get('/fup-profiles/', { params: tenantId ? { tenant_id: tenantId } : undefined })),
  getSalesAgents: (tenantId?: string) => unwrap<Record<string, unknown>[]>(http.get('/sales-agents/', { params: tenantId ? { tenant_id: tenantId } : undefined })),
  getCommissions: (tenantId?: string) => unwrap<Record<string, unknown>[]>(http.get('/commissions/', { params: tenantId ? { tenant_id: tenantId } : undefined })),

  // System Users (SuperAdmin)
  getSystemUsers: () => unwrap<SystemUser[]>(http.get('/superadmin/users/')),
  createSystemUser: (payload: Partial<SystemUser> & { password: string }) => unwrap<SystemUser>(http.post('/superadmin/users/', payload)),
  updateSystemUser: (id: number, payload: Partial<SystemUser>) => unwrap<SystemUser>(http.patch(`/superadmin/users/${id}/`, payload)),
  deleteSystemUser: (id: number) => http.delete(`/superadmin/users/${id}/`).then(() => undefined),

  // Customers (WISP Operations)
  getCustomers: (tenantId?: string) =>
    unwrap<Customer[]>(http.get('/customers/', { params: tenantId ? { tenant_id: tenantId } : undefined })),
  createCustomer: (payload: Partial<Customer> & { portal_password?: string }) =>
    unwrap<Customer>(http.post('/customers/', payload)),
  updateCustomer: (id: string, payload: Partial<Customer>) =>
    unwrap<Customer>(http.patch(`/customers/${id}/`, payload)),
  deleteCustomer: (id: string) => http.delete(`/customers/${id}/`).then(() => undefined),

  // Active Sessions & Manual Disconnect
  getActiveSessions: (tenantId?: string) =>
    unwrap<ActiveSession[]>(http.get('/sessions/active/', { params: tenantId ? { tenant_id: tenantId } : undefined })),
  getSessionHistory: (tenantId?: string) => unwrap<ActiveSession[]>(http.get('/sessions/history/', { params: tenantId ? { tenant_id: tenantId } : undefined })),
  getCustomerProfile: () => unwrap<Customer>(http.get('/customer/profile/')),
  changeCustomerPassword: (payload: { current_password: string; new_password: string }) =>
    unwrap<{ success: boolean }>(http.post('/customer/password/', payload)),
  disconnectSession: (sessionId: string) =>
    unwrap<{ success: boolean; message: string }>(http.post(`/sessions/${sessionId}/disconnect/`)),

  // Invoices & Billing
  getInvoices: (tenantId?: string) =>
    unwrap<Invoice[]>(http.get('/invoices/', { params: tenantId ? { tenant_id: tenantId } : undefined })),
  createInvoice: (payload: Partial<Invoice>) => unwrap<Invoice>(http.post('/invoices/', payload)),

  // Support Tickets
  getTickets: (tenantId?: string) =>
    unwrap<SupportTicket[]>(http.get('/tickets/', { params: tenantId ? { tenant_id: tenantId } : undefined })),
  createTicket: (payload: Partial<SupportTicket>) => unwrap<SupportTicket>(http.post('/tickets/', payload)),
  addTicketMessage: (ticketId: string, text: string) =>
    unwrap<TicketMessage>(http.post(`/tickets/${ticketId}/messages/`, { text })),
  updateTicketStatus: (ticketId: string, status: SupportTicket['status']) =>
    unwrap<SupportTicket>(http.patch(`/tickets/${ticketId}/`, { status })),

  // Platform Global Settings
  getPlatformSettings: () => unwrap<PlatformSettings>(http.get('/superadmin/settings/')),
  updatePlatformSettings: (payload: Partial<PlatformSettings>) =>
    unwrap<PlatformSettings>(http.patch('/superadmin/settings/', payload)),

  // Voucher Redemption & Self-Service
  redeemVoucher: async (code: string, mac: string) => {
    try {
      const res = await http.post<{ success: boolean; plan: string; duration_minutes: number; message: string }>('/vouchers/redeem/', { code, mac });
      return res.data;
    } catch (error) {
      throw new Error(apiErrorMessage(error, 'Unable to redeem voucher.'));
    }
  },
};
