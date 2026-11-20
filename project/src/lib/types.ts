export interface Tenant {
  id: string;
  business_name: string;
  email: string;
  phone_number: string;
  billing_email?: string;
  paystack_secret_key_set?: boolean;
  platform_commission_pct: number;
  status: 'ACTIVE' | 'SUSPENDED' | 'CLOSED' | 'PENDING' | 'active' | 'suspended' | 'closed' | 'pending';
  balance: number;
  logo_url: string;
  brand_color: string;
  welcome_headline: string;
  terms_of_service: string;
  created_at: string;
}

export interface Nas {
  id: string;
  tenant_id: string;
  nasname: string;
  shortname: string;
  nas_ip: string;
  mac_address: string;
  secret: string;
  api_port?: number;
  api_username?: string;
  radius_server_ip?: string;
  type: string;
  is_online: boolean;
  status?: 'online' | 'offline';
  last_ping: string;
  created_at: string;
}

export interface HotspotPlan {
  id: string;
  tenant_id: string;
  name: string;
  price: number;
  currency: 'KES';
  duration_minutes: number;
  duration_value: number;
  duration_unit: 'minutes' | 'hours' | 'days';
  download_speed_kbps: number;
  upload_speed_kbps: number;
  simultaneous_devices: number;
  is_active: boolean;
  created_at: string;
}

export interface Transaction {
  id: string;
  tenant_id: string;
  nas_id: string | null;
  plan_id: string | null;
  payment_ref: string;
  customer_phone: string;
  customer_mac: string;
  gross_amount: number;
  platform_fee: number;
  vendor_net_amount: number;
  gateway_fee: number;
  gateway_receipt: string;
  paid_at: string | null;
  payment_method: 'mobile_money' | 'card' | 'voucher' | 'MPESA' | 'PAYSTACK_MOBILE_MONEY' | 'VOUCHER';
  status: 'COMPLETED' | 'PENDING' | 'FAILED' | 'completed' | 'pending' | 'failed';
  created_at: string;
  updated_at: string;
}

export interface RadCheck {
  id: string;
  tenant_id: string;
  transaction_id: string | null;
  username: string;
  attribute: string;
  op: string;
  value: string;
  created_at: string;
}

export interface RadReply {
  id: string;
  tenant_id: string;
  transaction_id: string | null;
  username: string;
  attribute: string;
  op: string;
  value: string;
  created_at: string;
}

export interface SystemEvent {
  id: string;
  tenant_id: string | null;
  event_type: 'heartbeat' | 'alert' | 'payment' | 'system' | 'router';
  severity: 'info' | 'warning' | 'error' | 'success';
  message: string;
  created_at: string;
}

export type StaffRole = 'MANAGER' | 'TECHNICIAN' | 'CASHIER';

export interface StaffMember {
  id: number;
  username: string;
  email: string;
  role: StaffRole;
  is_active: boolean;
  created_at: string;
}

export interface SystemUser {
  id: number;
  username: string;
  email: string;
  role: 'SUPERADMIN' | 'SUPPORT_AGENT' | 'BILLING_ADMIN';
  is_active: boolean;
  last_login: string | null;
  created_at: string;
}

export interface Customer {
  id: string;
  tenant_id: string;
  username: string;
  name: string;
  phone_number: string;
  mac_address: string;
  service_type: 'hotspot' | 'pppoe';
  plan_id?: string;
  plan_name: string;
  pppoe_password?: string;
  status: 'active' | 'expired' | 'blocked' | 'pending';
  ip_address: string;
  uptime_seconds: number;
  download_bytes: number;
  upload_bytes: number;
  expires_at: string | null;
  created_at: string;
}

export interface ActiveSession {
  id: string;
  tenant_id: string;
  username: string;
  ip_address: string;
  mac_address: string;
  service_type: 'hotspot' | 'pppoe';
  uptime_seconds: number;
  rx_bytes: number;
  tx_bytes: number;
  started_at: string;
  router_name: string;
  stopped_at?: string | null;
  terminate_cause?: string;
}

export interface Invoice {
  id: string;
  tenant_id: string;
  invoice_number: string;
  customer_name: string;
  customer_phone: string;
  plan_name: string;
  amount: number;
  date: string;
  due_date: string;
  status: 'PAID' | 'UNPAID' | 'OVERDUE';
  payment_ref?: string;
}

export interface TicketMessage {
  id: string;
  sender: string;
  is_staff: boolean;
  text: string;
  created_at: string;
}

export interface SupportTicket {
  id: string;
  tenant_id: string;
  ticket_number: string;
  customer_name: string;
  customer_phone: string;
  subject: string;
  description: string;
  priority: 'LOW' | 'MEDIUM' | 'HIGH' | 'URGENT';
  status: 'OPEN' | 'IN_PROGRESS' | 'RESOLVED' | 'CLOSED';
  created_at: string;
  updated_at: string;
  messages: TicketMessage[];
}

export interface PlatformSettings {
  platform_name: string;
  currency: string;
  default_commission_pct: number;
  mpesa_paybill: string;
  mpesa_env: 'sandbox' | 'production';
  radius_auth_port: number;
  radius_acct_port: number;
  session_timeout_secs: number;
  support_email: string;
  maintenance_mode: boolean;
}

export type Role = 'superadmin' | 'vendor' | 'enduser';
