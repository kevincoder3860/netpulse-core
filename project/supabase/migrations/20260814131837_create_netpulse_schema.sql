/*
# NetPulse SaaS - Core Database Schema

## Overview
Creates the complete database schema for a multi-tenant Wi-Fi Hotspot & Router Management SaaS platform.
This is a demo/no-auth application with a role-switcher, so all tables use anon+authenticated policies.

## New Tables

1. `tenants` — Vendor/hotspot owner accounts (the tenants of the SaaS platform)
   - id (uuid PK)
   - business_name (text) — e.g. "Main Cafe Ltd"
   - email (text) — vendor contact email
   - platform_commission_pct (numeric) — commission rate the platform takes (e.g. 10.00)
   - status (text) — 'active' | 'suspended' | 'pending'
   - balance (numeric) — vendor's net earnings balance
   - logo_url (text) — branding logo URL for captive portal
   - brand_color (text) — hex color for captive portal accent
   - welcome_headline (text) — captive portal headline
   - terms_of_service (text) — captive portal TOS text
   - created_at (timestamptz)

2. `nas` — Network Access Servers (routers)
   - id (uuid PK)
   - tenant_id (uuid FK → tenants)
   - nasname (text) — router name/identifier
   - shortname (text) — venue location name e.g. "Main Cafe"
   - nas_ip (text) — IP address
   - mac_address (text) — MAC address
   - secret (text) — RADIUS shared secret
   - type (text) — router type e.g. "mikrotik"
   - is_online (boolean) — online/offline status
   - last_ping (timestamptz) — last heartbeat timestamp
   - created_at (timestamptz)

3. `hotspot_plans` — Wi-Fi packages sold to end-users
   - id (uuid PK)
   - tenant_id (uuid FK → tenants)
   - name (text) — package name e.g. "1 Hour Speed Boost"
   - price (numeric) — price in dollars
   - duration_minutes (integer) — session duration
   - max_download_kbps (integer) — download speed limit
   - max_upload_kbps (integer) — upload speed limit
   - max_devices (integer) — simultaneous device count
   - is_active (boolean) — whether the plan is available for purchase
   - created_at (timestamptz)

4. `transactions` — Customer payment records
   - id (uuid PK)
   - tenant_id (uuid FK → tenants)
   - nas_id (uuid FK → nas, nullable)
   - plan_id (uuid FK → hotspot_plans, nullable)
   - payment_ref (text) — unique payment reference
   - customer_phone (text) — customer phone number
   - customer_mac (text) — customer device MAC
   - gross_amount (numeric) — total paid
   - platform_fee (numeric) — platform commission cut
   - vendor_net_amount (numeric) — vendor's net earnings
   - payment_method (text) — 'mobile_money' | 'card' | 'voucher'
   - status (text) — 'completed' | 'pending' | 'failed'
   - created_at (timestamptz)

5. `radcheck` — FreeRADIUS access check (voucher credentials)
   - id (uuid PK)
   - tenant_id (uuid FK → tenants)
   - transaction_id (uuid FK → transactions, nullable)
   - username (text) — voucher/username
   - attribute (text) — RADIUS attribute e.g. "Cleartext-Password"
   - op (text) — operator e.g. ":="
   - value (text) — password value
   - created_at (timestamptz)

6. `radreply` — FreeRADIUS reply (session limits)
   - id (uuid PK)
   - tenant_id (uuid FK → tenants)
   - transaction_id (uuid FK → transactions, nullable)
   - username (text) — matching radcheck username
   - attribute (text) — RADIUS attribute e.g. "Session-Timeout", "Mikrotik-Rate-Limit"
   - op (text) — operator e.g. ":="
   - value (text) — attribute value
   - created_at (timestamptz)

7. `system_events` — Global system health log
   - id (uuid PK)
   - tenant_id (uuid FK → tenants, nullable)
   - event_type (text) — 'heartbeat' | 'alert' | 'payment' | 'system' | 'router'
   - severity (text) — 'info' | 'warning' | 'error' | 'success'
   - message (text) — event description
   - created_at (timestamptz)

## Security
- RLS enabled on all tables.
- All tables allow anon+authenticated CRUD (demo app with role-switcher, no real auth).
- USING (true) is acceptable here because this is a single-tenant demo with no sign-in.
*/

-- ============ TENANTS ============
CREATE TABLE IF NOT EXISTS tenants (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  business_name text NOT NULL,
  email text NOT NULL,
  platform_commission_pct numeric DEFAULT 10.00,
  status text NOT NULL DEFAULT 'active',
  balance numeric DEFAULT 0,
  logo_url text DEFAULT '',
  brand_color text DEFAULT '#6366f1',
  welcome_headline text DEFAULT 'Welcome to our Wi-Fi',
  terms_of_service text DEFAULT 'By connecting you agree to our terms of service.',
  created_at timestamptz DEFAULT now()
);
ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "anon_crud_tenants_select" ON tenants;
CREATE POLICY "anon_crud_tenants_select" ON tenants FOR SELECT TO anon, authenticated USING (true);
DROP POLICY IF EXISTS "anon_crud_tenants_insert" ON tenants;
CREATE POLICY "anon_crud_tenants_insert" ON tenants FOR INSERT TO anon, authenticated WITH CHECK (true);
DROP POLICY IF EXISTS "anon_crud_tenants_update" ON tenants;
CREATE POLICY "anon_crud_tenants_update" ON tenants FOR UPDATE TO anon, authenticated USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS "anon_crud_tenants_delete" ON tenants;
CREATE POLICY "anon_crud_tenants_delete" ON tenants FOR DELETE TO anon, authenticated USING (true);

-- ============ NAS (ROUTERS) ============
CREATE TABLE IF NOT EXISTS nas (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  nasname text NOT NULL,
  shortname text DEFAULT '',
  nas_ip text DEFAULT '',
  mac_address text DEFAULT '',
  secret text DEFAULT '',
  type text DEFAULT 'mikrotik',
  is_online boolean DEFAULT true,
  last_ping timestamptz DEFAULT now(),
  created_at timestamptz DEFAULT now()
);
ALTER TABLE nas ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "anon_crud_nas_select" ON nas;
CREATE POLICY "anon_crud_nas_select" ON nas FOR SELECT TO anon, authenticated USING (true);
DROP POLICY IF EXISTS "anon_crud_nas_insert" ON nas;
CREATE POLICY "anon_crud_nas_insert" ON nas FOR INSERT TO anon, authenticated WITH CHECK (true);
DROP POLICY IF EXISTS "anon_crud_nas_update" ON nas;
CREATE POLICY "anon_crud_nas_update" ON nas FOR UPDATE TO anon, authenticated USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS "anon_crud_nas_delete" ON nas;
CREATE POLICY "anon_crud_nas_delete" ON nas FOR DELETE TO anon, authenticated USING (true);

-- ============ HOTSPOT PLANS ============
CREATE TABLE IF NOT EXISTS hotspot_plans (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  name text NOT NULL,
  price numeric NOT NULL DEFAULT 0,
  duration_minutes integer NOT NULL DEFAULT 60,
  max_download_kbps integer DEFAULT 1024,
  max_upload_kbps integer DEFAULT 512,
  max_devices integer DEFAULT 1,
  is_active boolean DEFAULT true,
  created_at timestamptz DEFAULT now()
);
ALTER TABLE hotspot_plans ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "anon_crud_plans_select" ON hotspot_plans;
CREATE POLICY "anon_crud_plans_select" ON hotspot_plans FOR SELECT TO anon, authenticated USING (true);
DROP POLICY IF EXISTS "anon_crud_plans_insert" ON hotspot_plans;
CREATE POLICY "anon_crud_plans_insert" ON hotspot_plans FOR INSERT TO anon, authenticated WITH CHECK (true);
DROP POLICY IF EXISTS "anon_crud_plans_update" ON hotspot_plans;
CREATE POLICY "anon_crud_plans_update" ON hotspot_plans FOR UPDATE TO anon, authenticated USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS "anon_crud_plans_delete" ON hotspot_plans;
CREATE POLICY "anon_crud_plans_delete" ON hotspot_plans FOR DELETE TO anon, authenticated USING (true);

-- ============ TRANSACTIONS ============
CREATE TABLE IF NOT EXISTS transactions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  nas_id uuid REFERENCES nas(id) ON DELETE SET NULL,
  plan_id uuid REFERENCES hotspot_plans(id) ON DELETE SET NULL,
  payment_ref text NOT NULL,
  customer_phone text DEFAULT '',
  customer_mac text DEFAULT '',
  gross_amount numeric NOT NULL DEFAULT 0,
  platform_fee numeric NOT NULL DEFAULT 0,
  vendor_net_amount numeric NOT NULL DEFAULT 0,
  payment_method text DEFAULT 'mobile_money',
  status text DEFAULT 'completed',
  created_at timestamptz DEFAULT now()
);
ALTER TABLE transactions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "anon_crud_tx_select" ON transactions;
CREATE POLICY "anon_crud_tx_select" ON transactions FOR SELECT TO anon, authenticated USING (true);
DROP POLICY IF EXISTS "anon_crud_tx_insert" ON transactions;
CREATE POLICY "anon_crud_tx_insert" ON transactions FOR INSERT TO anon, authenticated WITH CHECK (true);
DROP POLICY IF EXISTS "anon_crud_tx_update" ON transactions;
CREATE POLICY "anon_crud_tx_update" ON transactions FOR UPDATE TO anon, authenticated USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS "anon_crud_tx_delete" ON transactions;
CREATE POLICY "anon_crud_tx_delete" ON transactions FOR DELETE TO anon, authenticated USING (true);

-- ============ RADCHECK ============
CREATE TABLE IF NOT EXISTS radcheck (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  transaction_id uuid REFERENCES transactions(id) ON DELETE SET NULL,
  username text NOT NULL,
  attribute text DEFAULT 'Cleartext-Password',
  op text DEFAULT ':=',
  value text NOT NULL,
  created_at timestamptz DEFAULT now()
);
ALTER TABLE radcheck ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "anon_crud_radcheck_select" ON radcheck;
CREATE POLICY "anon_crud_radcheck_select" ON radcheck FOR SELECT TO anon, authenticated USING (true);
DROP POLICY IF EXISTS "anon_crud_radcheck_insert" ON radcheck;
CREATE POLICY "anon_crud_radcheck_insert" ON radcheck FOR INSERT TO anon, authenticated WITH CHECK (true);
DROP POLICY IF EXISTS "anon_crud_radcheck_update" ON radcheck;
CREATE POLICY "anon_crud_radcheck_update" ON radcheck FOR UPDATE TO anon, authenticated USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS "anon_crud_radcheck_delete" ON radcheck;
CREATE POLICY "anon_crud_radcheck_delete" ON radcheck FOR DELETE TO anon, authenticated USING (true);

-- ============ RADREPLY ============
CREATE TABLE IF NOT EXISTS radreply (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  transaction_id uuid REFERENCES transactions(id) ON DELETE SET NULL,
  username text NOT NULL,
  attribute text NOT NULL,
  op text DEFAULT ':=',
  value text NOT NULL,
  created_at timestamptz DEFAULT now()
);
ALTER TABLE radreply ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "anon_crud_radreply_select" ON radreply;
CREATE POLICY "anon_crud_radreply_select" ON radreply FOR SELECT TO anon, authenticated USING (true);
DROP POLICY IF EXISTS "anon_crud_radreply_insert" ON radreply;
CREATE POLICY "anon_crud_radreply_insert" ON radreply FOR INSERT TO anon, authenticated WITH CHECK (true);
DROP POLICY IF EXISTS "anon_crud_radreply_update" ON radreply;
CREATE POLICY "anon_crud_radreply_update" ON radreply FOR UPDATE TO anon, authenticated USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS "anon_crud_radreply_delete" ON radreply;
CREATE POLICY "anon_crud_radreply_delete" ON radreply FOR DELETE TO anon, authenticated USING (true);

-- ============ SYSTEM EVENTS ============
CREATE TABLE IF NOT EXISTS system_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid REFERENCES tenants(id) ON DELETE SET NULL,
  event_type text NOT NULL DEFAULT 'system',
  severity text NOT NULL DEFAULT 'info',
  message text NOT NULL,
  created_at timestamptz DEFAULT now()
);
ALTER TABLE system_events ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "anon_crud_events_select" ON system_events;
CREATE POLICY "anon_crud_events_select" ON system_events FOR SELECT TO anon, authenticated USING (true);
DROP POLICY IF EXISTS "anon_crud_events_insert" ON system_events;
CREATE POLICY "anon_crud_events_insert" ON system_events FOR INSERT TO anon, authenticated WITH CHECK (true);
DROP POLICY IF EXISTS "anon_crud_events_update" ON system_events;
CREATE POLICY "anon_crud_events_update" ON system_events FOR UPDATE TO anon, authenticated USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS "anon_crud_events_delete" ON system_events;
CREATE POLICY "anon_crud_events_delete" ON system_events FOR DELETE TO anon, authenticated USING (true);

-- ============ INDEXES ============
CREATE INDEX IF NOT EXISTS idx_nas_tenant ON nas(tenant_id);
CREATE INDEX IF NOT EXISTS idx_plans_tenant ON hotspot_plans(tenant_id);
CREATE INDEX IF NOT EXISTS idx_tx_tenant ON transactions(tenant_id);
CREATE INDEX IF NOT EXISTS idx_tx_created ON transactions(created_at);
CREATE INDEX IF NOT EXISTS idx_events_created ON system_events(created_at);
CREATE INDEX IF NOT EXISTS idx_radcheck_tenant ON radcheck(tenant_id);
CREATE INDEX IF NOT EXISTS idx_radreply_tenant ON radreply(tenant_id);
