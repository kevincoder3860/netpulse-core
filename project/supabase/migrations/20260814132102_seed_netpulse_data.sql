/*
# NetPulse SaaS - Seed Data

## Overview
Populates all tables with realistic sample data for the demo:
- 5 tenants (vendors) with varied statuses, commission rates, and branding
- 12 NAS routers across tenants with online/offline mix
- 12 hotspot plans across tenants
- 30 transactions spread over the last 30 days
- radcheck/radreply entries for voucher simulation
- 20+ system events for the health log

## Important Notes
1. Uses fixed UUIDs for tenants so child records can reference them.
2. All data is fictional but realistic for a Wi-Fi hotspot SaaS.
3. Transaction amounts, fees, and vendor nets are internally consistent.
4. ON CONFLICT clauses are at the END of each multi-row INSERT (PostgreSQL syntax).
*/

-- ============ TENANTS ============
INSERT INTO tenants (id, business_name, email, platform_commission_pct, status, balance, logo_url, brand_color, welcome_headline, terms_of_service) VALUES
('a1000000-0000-0000-0000-000000000001', 'Java Junction Cafe', 'owner@javajunction.co', 10.00, 'active', 2847.50, 'https://images.pexels.com/photos/302899/pexels-photo-302899.jpeg?auto=compress&cs=tinysrgb&w=200', '#6366f1', 'Welcome to Java Junction Wi-Fi! Grab a coffee and get connected.', 'By connecting to Java Junction Wi-Fi, you agree to our acceptable use policy. No illegal activity. Bandwidth is shared among all guests.'),
('a1000000-0000-0000-0000-000000000002', 'Skyline Hotel Group', 'it@skylinehotels.com', 12.00, 'active', 15230.00, 'https://images.pexels.com/photos/261101/pexels-photo-261101.jpeg?auto=compress&cs=tinysrgb&w=200', '#10b981', 'Welcome to Skyline Hotels Premium Wi-Fi. Enjoy your stay.', 'By using Skyline Hotels Wi-Fi, you agree to our terms. Premium bandwidth for hotel guests. Fair use applies.'),
('a1000000-0000-0000-0000-000000000003', 'Campus Connect ISP', 'admin@campusconnect.edu', 8.00, 'active', 8900.25, '', '#f59e0b', 'Campus Connect - Student Wi-Fi Portal', 'By connecting, students agree to the university acceptable use policy. Academic use only.'),
('a1000000-0000-0000-0000-000000000004', 'Riverside Resort & Spa', 'manager@riverside.fun', 15.00, 'pending', 0, '', '#ef4444', 'Welcome to Riverside Resort Wi-Fi', 'By connecting to Riverside Resort Wi-Fi, you agree to our guest terms.'),
('a1000000-0000-0000-0000-000000000005', 'Transit Mesh Networks', 'ops@transitmesh.io', 10.00, 'suspended', 450.00, '', '#8b5cf6', 'Transit Mesh - Public Wi-Fi Portal', 'By using Transit Mesh public Wi-Fi, you agree to our community guidelines.')
ON CONFLICT (id) DO NOTHING;

-- ============ NAS (ROUTERS) ============
INSERT INTO nas (id, tenant_id, nasname, shortname, nas_ip, mac_address, secret, type, is_online, last_ping) VALUES
('b2000000-0000-0000-0000-000000000001', 'a1000000-0000-0000-0000-000000000001', 'MT-CAFE-01', 'Main Cafe', '10.10.1.1', '48:8F:5A:1A:2B:3C', 's3cr3tCafe2024!', 'mikrotik', true, now() - interval '2 minutes'),
('b2000000-0000-0000-0000-000000000002', 'a1000000-0000-0000-0000-000000000001', 'MT-CAFE-02', 'Outdoor Patio', '10.10.1.2', '48:8F:5A:1A:2B:3D', 's3cr3tPatio2024!', 'mikrotik', true, now() - interval '5 minutes'),
('b2000000-0000-0000-0000-000000000003', 'a1000000-0000-0000-0000-000000000002', 'MT-HOTEL-01', 'Lobby', '10.20.1.1', 'D4:CA:6E:AA:11:22', 'skylineL0bby!23', 'mikrotik', true, now() - interval '1 minutes'),
('b2000000-0000-0000-0000-000000000004', 'a1000000-0000-0000-0000-000000000002', 'MT-HOTEL-02', 'Conference Room A', '10.20.1.2', 'D4:CA:6E:AA:11:23', 'skylineC0nf!23', 'mikrotik', true, now() - interval '3 minutes'),
('b2000000-0000-0000-0000-000000000005', 'a1000000-0000-0000-0000-000000000002', 'MT-HOTEL-03', 'Pool Deck', '10.20.1.3', 'D4:CA:6E:AA:11:24', 'skylineP00l!23', 'mikrotik', false, now() - interval '2 hours'),
('b2000000-0000-0000-0000-000000000006', 'a1000000-0000-0000-0000-000000000003', 'MT-CAMPUS-01', 'Library', '10.30.1.1', 'E0:63:DA:BB:33:11', 'campusLib!234', 'mikrotik', true, now() - interval '1 minutes'),
('b2000000-0000-0000-0000-000000000007', 'a1000000-0000-0000-0000-000000000003', 'MT-CAMPUS-02', 'Student Union', '10.30.1.2', 'E0:63:DA:BB:33:12', 'campusUni0n!23', 'mikrotik', true, now() - interval '4 minutes'),
('b2000000-0000-0000-0000-000000000008', 'a1000000-0000-0000-0000-000000000003', 'MT-CAMPUS-03', 'Dormitory Block B', '10.30.1.3', 'E0:63:DA:BB:33:13', 'campusD0rm!23', 'mikrotik', false, now() - interval '45 minutes'),
('b2000000-0000-0000-0000-000000000009', 'a1000000-0000-0000-0000-000000000004', 'MT-RESORT-01', 'Main Lobby', '10.40.1.1', 'C8:60:0C:CC:55:11', 'riversideM4in!', 'mikrotik', true, now() - interval '10 minutes'),
('b2000000-0000-0000-0000-000000000010', 'a1000000-0000-0000-0000-000000000004', 'MT-RESORT-02', 'Beach Bar', '10.40.1.2', 'C8:60:0C:CC:55:12', 'riversideB34ch', 'mikrotik', true, now() - interval '7 minutes'),
('b2000000-0000-0000-0000-000000000011', 'a1000000-0000-0000-0000-000000000005', 'MT-TRANSIT-01', 'Central Station', '10.50.1.1', 'B8:27:EB:DD:66:11', 'transitCentr4l', 'mikrotik', false, now() - interval '3 hours'),
('b2000000-0000-0000-0000-000000000012', 'a1000000-0000-0000-0000-000000000005', 'MT-TRANSIT-02', 'North Terminal', '10.50.1.2', 'B8:27:EB:DD:66:12', 'transitN0rth!', 'mikrotik', false, now() - interval '5 hours')
ON CONFLICT (id) DO NOTHING;

-- ============ HOTSPOT PLANS ============
INSERT INTO hotspot_plans (id, tenant_id, name, price, duration_minutes, max_download_kbps, max_upload_kbps, max_devices, is_active) VALUES
('c3000000-0000-0000-0000-000000000001', 'a1000000-0000-0000-0000-000000000001', '30 Min Quick Browse', 0.50, 30, 2048, 1024, 1, true),
('c3000000-0000-0000-0000-000000000002', 'a1000000-0000-0000-0000-000000000001', '1 Hour Speed Boost', 0.50, 60, 5120, 2048, 1, true),
('c3000000-0000-0000-0000-000000000003', 'a1000000-0000-0000-0000-000000000001', '24 Hour Unlimited', 3.00, 1440, 10240, 5120, 3, true),
('c3000000-0000-0000-0000-000000000004', 'a1000000-0000-0000-0000-000000000002', '1 Hour Standard', 2.00, 60, 5120, 2048, 1, true),
('c3000000-0000-0000-0000-000000000005', 'a1000000-0000-0000-0000-000000000002', '24 Hour Premium', 8.00, 1440, 20480, 10240, 2, true),
('c3000000-0000-0000-0000-000000000006', 'a1000000-0000-0000-0000-000000000002', '7 Day Business', 25.00, 10080, 20480, 10240, 5, true),
('c3000000-0000-0000-0000-000000000007', 'a1000000-0000-0000-0000-000000000003', 'Student 1 Hour', 0.25, 60, 2048, 1024, 1, true),
('c3000000-0000-0000-0000-000000000008', 'a1000000-0000-0000-0000-000000000003', 'Student 6 Hour', 0.75, 360, 4096, 2048, 1, true),
('c3000000-0000-0000-0000-000000000009', 'a1000000-0000-0000-0000-000000000003', 'Student 24 Hour', 1.50, 1440, 5120, 2048, 2, true),
('c3000000-0000-0000-0000-000000000010', 'a1000000-0000-0000-0000-000000000004', '1 Hour Guest', 1.00, 60, 5120, 2048, 1, true),
('c3000000-0000-0000-0000-000000000011', 'a1000000-0000-0000-0000-000000000004', '24 Hour Guest', 5.00, 1440, 10240, 5120, 2, true),
('c3000000-0000-0000-0000-000000000012', 'a1000000-0000-0000-0000-000000000005', '30 Min Transit', 0.25, 30, 1024, 512, 1, true)
ON CONFLICT (id) DO NOTHING;

-- ============ TRANSACTIONS ============
INSERT INTO transactions (id, tenant_id, nas_id, plan_id, payment_ref, customer_phone, customer_mac, gross_amount, platform_fee, vendor_net_amount, payment_method, status, created_at) VALUES
-- Java Junction Cafe (10% commission)
('d4000000-0000-0000-0000-000000000001', 'a1000000-0000-0000-0000-000000000001', 'b2000000-0000-0000-0000-000000000001', 'c3000000-0000-0000-0000-000000000002', 'NP-001-JA', '+254712345678', 'A4:B1:C2:D3:E4:F1', 0.50, 0.05, 0.45, 'mobile_money', 'completed', now() - interval '1 hour'),
('d4000000-0000-0000-0000-000000000002', 'a1000000-0000-0000-0000-000000000001', 'b2000000-0000-0000-0000-000000000001', 'c3000000-0000-0000-0000-000000000003', 'NP-002-JB', '+254723456789', 'A4:B1:C2:D3:E4:F2', 3.00, 0.30, 2.70, 'mobile_money', 'completed', now() - interval '3 hours'),
('d4000000-0000-0000-0000-000000000003', 'a1000000-0000-0000-0000-000000000001', 'b2000000-0000-0000-0000-000000000002', 'c3000000-0000-0000-0000-000000000001', 'NP-003-JC', '+254734567890', 'A4:B1:C2:D3:E4:F3', 0.50, 0.05, 0.45, 'card', 'completed', now() - interval '5 hours'),
('d4000000-0000-0000-0000-000000000004', 'a1000000-0000-0000-0000-000000000001', 'b2000000-0000-0000-0000-000000000001', 'c3000000-0000-0000-0000-000000000003', 'NP-004-JD', '+254745678901', 'A4:B1:C2:D3:E4:F4', 3.00, 0.30, 2.70, 'voucher', 'completed', now() - interval '8 hours'),
('d4000000-0000-0000-0000-000000000005', 'a1000000-0000-0000-0000-000000000001', 'b2000000-0000-0000-0000-000000000002', 'c3000000-0000-0000-0000-000000000002', 'NP-005-JE', '+254756789012', 'A4:B1:C2:D3:E4:F5', 0.50, 0.05, 0.45, 'mobile_money', 'completed', now() - interval '12 hours'),
('d4000000-0000-0000-0000-000000000006', 'a1000000-0000-0000-0000-000000000001', 'b2000000-0000-0000-0000-000000000001', 'c3000000-0000-0000-0000-000000000003', 'NP-006-JF', '+254767890123', 'A4:B1:C2:D3:E4:F6', 3.00, 0.30, 2.70, 'mobile_money', 'completed', now() - interval '1 day'),
('d4000000-0000-0000-0000-000000000007', 'a1000000-0000-0000-0000-000000000001', 'b2000000-0000-0000-0000-000000000001', 'c3000000-0000-0000-0000-000000000001', 'NP-007-JG', '+254778901234', 'A4:B1:C2:D3:E4:F7', 0.50, 0.05, 0.45, 'mobile_money', 'completed', now() - interval '1 day 4 hours'),
('d4000000-0000-0000-0000-000000000008', 'a1000000-0000-0000-0000-000000000001', 'b2000000-0000-0000-0000-000000000002', 'c3000000-0000-0000-0000-000000000003', 'NP-008-JH', '+254789012345', 'A4:B1:C2:D3:E4:F8', 3.00, 0.30, 2.70, 'card', 'completed', now() - interval '2 days'),
('d4000000-0000-0000-0000-000000000009', 'a1000000-0000-0000-0000-000000000001', 'b2000000-0000-0000-0000-000000000001', 'c3000000-0000-0000-0000-000000000002', 'NP-009-JI', '+254790123456', 'A4:B1:C2:D3:E4:F9', 0.50, 0.05, 0.45, 'mobile_money', 'completed', now() - interval '2 days 6 hours'),
('d4000000-0000-0000-0000-000000000010', 'a1000000-0000-0000-0000-000000000001', 'b2000000-0000-0000-0000-000000000001', 'c3000000-0000-0000-0000-000000000003', 'NP-010-JJ', '+254701234567', 'A4:B1:C2:D3:E4:FA', 3.00, 0.30, 2.70, 'mobile_money', 'completed', now() - interval '3 days'),
-- Skyline Hotel Group (12% commission)
('d4000000-0000-0000-0000-000000000011', 'a1000000-0000-0000-0000-000000000002', 'b2000000-0000-0000-0000-000000000003', 'c3000000-0000-0000-0000-000000000005', 'NP-011-SA', '+254711122233', 'B4:C1:D2:E3:F4:01', 8.00, 0.96, 7.04, 'card', 'completed', now() - interval '2 hours'),
('d4000000-0000-0000-0000-000000000012', 'a1000000-0000-0000-0000-000000000002', 'b2000000-0000-0000-0000-000000000003', 'c3000000-0000-0000-0000-000000000006', 'NP-012-SB', '+254722233344', 'B4:C1:D2:E3:F4:02', 25.00, 3.00, 22.00, 'card', 'completed', now() - interval '6 hours'),
('d4000000-0000-0000-0000-000000000013', 'a1000000-0000-0000-0000-000000000002', 'b2000000-0000-0000-0000-000000000004', 'c3000000-0000-0000-0000-000000000004', 'NP-013-SC', '+254733344455', 'B4:C1:D2:E3:F4:03', 2.00, 0.24, 1.76, 'mobile_money', 'completed', now() - interval '10 hours'),
('d4000000-0000-0000-0000-000000000014', 'a1000000-0000-0000-0000-000000000002', 'b2000000-0000-0000-0000-000000000003', 'c3000000-0000-0000-0000-000000000005', 'NP-014-SD', '+254744455566', 'B4:C1:D2:E3:F4:04', 8.00, 0.96, 7.04, 'card', 'completed', now() - interval '1 day 2 hours'),
('d4000000-0000-0000-0000-000000000015', 'a1000000-0000-0000-0000-000000000002', 'b2000000-0000-0000-0000-000000000004', 'c3000000-0000-0000-0000-000000000006', 'NP-015-SE', '+254755566677', 'B4:C1:D2:E3:F4:05', 25.00, 3.00, 22.00, 'card', 'completed', now() - interval '2 days 3 hours'),
('d4000000-0000-0000-0000-000000000016', 'a1000000-0000-0000-0000-000000000002', 'b2000000-0000-0000-0000-000000000003', 'c3000000-0000-0000-0000-000000000004', 'NP-016-SF', '+254766677788', 'B4:C1:D2:E3:F4:06', 2.00, 0.24, 1.76, 'mobile_money', 'completed', now() - interval '3 days 5 hours'),
('d4000000-0000-0000-0000-000000000017', 'a1000000-0000-0000-0000-000000000002', 'b2000000-0000-0000-0000-000000000003', 'c3000000-0000-0000-0000-000000000005', 'NP-017-SG', '+254777788899', 'B4:C1:D2:E3:F4:07', 8.00, 0.96, 7.04, 'card', 'completed', now() - interval '4 days'),
('d4000000-0000-0000-0000-000000000018', 'a1000000-0000-0000-0000-000000000002', 'b2000000-0000-0000-0000-000000000004', 'c3000000-0000-0000-0000-000000000005', 'NP-018-SH', '+254788899900', 'B4:C1:D2:E3:F4:08', 8.00, 0.96, 7.04, 'card', 'completed', now() - interval '5 days'),
-- Campus Connect ISP (8% commission)
('d4000000-0000-0000-0000-000000000019', 'a1000000-0000-0000-0000-000000000003', 'b2000000-0000-0000-0000-000000000006', 'c3000000-0000-0000-0000-000000000008', 'NP-019-CA', '+254711100011', 'C4:D1:E2:F3:G4:01', 0.75, 0.06, 0.69, 'mobile_money', 'completed', now() - interval '1 hour'),
('d4000000-0000-0000-0000-000000000020', 'a1000000-0000-0000-0000-000000000003', 'b2000000-0000-0000-0000-000000000006', 'c3000000-0000-0000-0000-000000000009', 'NP-020-CB', '+254722200022', 'C4:D1:E2:F3:G4:02', 1.50, 0.12, 1.38, 'mobile_money', 'completed', now() - interval '4 hours'),
('d4000000-0000-0000-0000-000000000021', 'a1000000-0000-0000-0000-000000000003', 'b2000000-0000-0000-0000-000000000007', 'c3000000-0000-0000-0000-000000000007', 'NP-021-CC', '+254733300033', 'C4:D1:E2:F3:G4:03', 0.25, 0.02, 0.23, 'voucher', 'completed', now() - interval '7 hours'),
('d4000000-0000-0000-0000-000000000022', 'a1000000-0000-0000-0000-000000000003', 'b2000000-0000-0000-0000-000000000006', 'c3000000-0000-0000-0000-000000000008', 'NP-022-CD', '+254744400044', 'C4:D1:E2:F3:G4:04', 0.75, 0.06, 0.69, 'mobile_money', 'completed', now() - interval '1 day 1 hour'),
('d4000000-0000-0000-0000-000000000023', 'a1000000-0000-0000-0000-000000000003', 'b2000000-0000-0000-0000-000000000007', 'c3000000-0000-0000-0000-000000000009', 'NP-023-CE', '+254755500055', 'C4:D1:E2:F3:G4:05', 1.50, 0.12, 1.38, 'mobile_money', 'completed', now() - interval '2 days 2 hours'),
('d4000000-0000-0000-0000-000000000024', 'a1000000-0000-0000-0000-000000000003', 'b2000000-0000-0000-0000-000000000006', 'c3000000-0000-0000-0000-000000000007', 'NP-024-CF', '+254766600066', 'C4:D1:E2:F3:G4:06', 0.25, 0.02, 0.23, 'voucher', 'completed', now() - interval '3 days 3 hours'),
-- Riverside Resort (15% commission)
('d4000000-0000-0000-0000-000000000025', 'a1000000-0000-0000-0000-000000000004', 'b2000000-0000-0000-0000-000000000009', 'c3000000-0000-0000-0000-000000000010', 'NP-025-RA', '+254711100099', 'D4:E1:F2:G3:H4:01', 1.00, 0.15, 0.85, 'mobile_money', 'completed', now() - interval '3 hours'),
('d4000000-0000-0000-0000-000000000026', 'a1000000-0000-0000-0000-000000000004', 'b2000000-0000-0000-0000-000000000010', 'c3000000-0000-0000-0000-000000000011', 'NP-026-RB', '+254722200088', 'D4:E1:F2:G3:H4:02', 5.00, 0.75, 4.25, 'card', 'completed', now() - interval '1 day'),
-- Transit Mesh (10% commission, suspended)
('d4000000-0000-0000-0000-000000000027', 'a1000000-0000-0000-0000-000000000005', 'b2000000-0000-0000-0000-000000000011', 'c3000000-0000-0000-0000-000000000012', 'NP-027-TA', '+254711100077', 'E4:F1:G2:H3:I4:01', 0.25, 0.025, 0.225, 'mobile_money', 'completed', now() - interval '2 days'),
('d4000000-0000-0000-0000-000000000028', 'a1000000-0000-0000-0000-000000000005', 'b2000000-0000-0000-0000-000000000011', 'c3000000-0000-0000-0000-000000000012', 'NP-028-TB', '+254722200066', 'E4:F1:G2:H3:I4:02', 0.25, 0.025, 0.225, 'mobile_money', 'completed', now() - interval '4 days'),
('d4000000-0000-0000-0000-000000000029', 'a1000000-0000-0000-0000-000000000005', 'b2000000-0000-0000-0000-000000000012', 'c3000000-0000-0000-0000-000000000012', 'NP-029-TC', '+254733300055', 'E4:F1:G2:H3:I4:03', 0.25, 0.025, 0.225, 'voucher', 'completed', now() - interval '6 days'),
('d4000000-0000-0000-0000-000000000030', 'a1000000-0000-0000-0000-000000000005', 'b2000000-0000-0000-0000-000000000011', 'c3000000-0000-0000-0000-000000000012', 'NP-030-TD', '+254744400044', 'E4:F1:G2:H3:I4:04', 0.25, 0.025, 0.225, 'mobile_money', 'completed', now() - interval '8 days')
ON CONFLICT (id) DO NOTHING;

-- ============ RADCHECK (voucher credentials) ============
INSERT INTO radcheck (tenant_id, transaction_id, username, attribute, op, value) VALUES
('a1000000-0000-0000-0000-000000000001', 'd4000000-0000-0000-0000-000000000001', 'NP-001-JA', 'Cleartext-Password', ':=', 'pass-001-JA'),
('a1000000-0000-0000-0000-000000000001', 'd4000000-0000-0000-0000-000000000002', 'NP-002-JB', 'Cleartext-Password', ':=', 'pass-002-JB'),
('a1000000-0000-0000-0000-000000000002', 'd4000000-0000-0000-0000-000000000011', 'NP-011-SA', 'Cleartext-Password', ':=', 'pass-011-SA'),
('a1000000-0000-0000-0000-000000000002', 'd4000000-0000-0000-0000-000000000012', 'NP-012-SB', 'Cleartext-Password', ':=', 'pass-012-SB'),
('a1000000-0000-0000-0000-000000000003', 'd4000000-0000-0000-0000-000000000019', 'NP-019-CA', 'Cleartext-Password', ':=', 'pass-019-CA'),
('a1000000-0000-0000-0000-000000000003', 'd4000000-0000-0000-0000-000000000020', 'NP-020-CB', 'Cleartext-Password', ':=', 'pass-020-CB')
ON CONFLICT DO NOTHING;

-- ============ RADREPLY (session limits) ============
INSERT INTO radreply (tenant_id, transaction_id, username, attribute, op, value) VALUES
('a1000000-0000-0000-0000-000000000001', 'd4000000-0000-0000-0000-000000000001', 'NP-001-JA', 'Session-Timeout', ':=', '3600'),
('a1000000-0000-0000-0000-000000000001', 'd4000000-0000-0000-0000-000000000001', 'NP-001-JA', 'Mikrotik-Rate-Limit', ':=', '5120k/2048k'),
('a1000000-0000-0000-0000-000000000001', 'd4000000-0000-0000-0000-000000000002', 'NP-002-JB', 'Session-Timeout', ':=', '86400'),
('a1000000-0000-0000-0000-000000000001', 'd4000000-0000-0000-0000-000000000002', 'NP-002-JB', 'Mikrotik-Rate-Limit', ':=', '10240k/5120k'),
('a1000000-0000-0000-0000-000000000002', 'd4000000-0000-0000-0000-000000000011', 'NP-011-SA', 'Session-Timeout', ':=', '86400'),
('a1000000-0000-0000-0000-000000000002', 'd4000000-0000-0000-0000-000000000011', 'NP-011-SA', 'Mikrotik-Rate-Limit', ':=', '20480k/10240k'),
('a1000000-0000-0000-0000-000000000002', 'd4000000-0000-0000-0000-000000000012', 'NP-012-SB', 'Session-Timeout', ':=', '604800'),
('a1000000-0000-0000-0000-000000000002', 'd4000000-0000-0000-0000-000000000012', 'NP-012-SB', 'Mikrotik-Rate-Limit', ':=', '20480k/10240k'),
('a1000000-0000-0000-0000-000000000003', 'd4000000-0000-0000-0000-000000000019', 'NP-019-CA', 'Session-Timeout', ':=', '21600'),
('a1000000-0000-0000-0000-000000000003', 'd4000000-0000-0000-0000-000000000019', 'NP-019-CA', 'Mikrotik-Rate-Limit', ':=', '4096k/2048k')
ON CONFLICT DO NOTHING;

-- ============ SYSTEM EVENTS ============
INSERT INTO system_events (tenant_id, event_type, severity, message) VALUES
('a1000000-0000-0000-0000-000000000001', 'heartbeat', 'success', 'Router MT-CAFE-01 heartbeat received — uptime 14d 3h 22m'),
('a1000000-0000-0000-0000-000000000001', 'heartbeat', 'success', 'Router MT-CAFE-02 heartbeat received — uptime 7d 11h 5m'),
('a1000000-0000-0000-0000-000000000002', 'heartbeat', 'success', 'Router MT-HOTEL-01 heartbeat received — uptime 30d 2h 15m'),
('a1000000-0000-0000-0000-000000000002', 'heartbeat', 'success', 'Router MT-HOTEL-02 heartbeat received — uptime 21d 8h 44m'),
('a1000000-0000-0000-0000-000000000002', 'router', 'error', 'Router MT-HOTEL-03 (Pool Deck) went OFFLINE — no heartbeat for 2h+'),
('a1000000-0000-0000-0000-000000000003', 'heartbeat', 'success', 'Router MT-CAMPUS-01 heartbeat received — uptime 45d 12h'),
('a1000000-0000-0000-0000-000000000003', 'router', 'warning', 'Router MT-CAMPUS-03 (Dormitory Block B) missed 3 consecutive heartbeats'),
('a1000000-0000-0000-0000-000000000004', 'system', 'info', 'New vendor onboarded: Riverside Resort & Spa — awaiting configuration'),
('a1000000-0000-0000-0000-000000000005', 'system', 'warning', 'Vendor Transit Mesh Networks suspended — billing failure'),
(NULL, 'payment', 'success', 'Payment webhook received: NP-011-SA $8.00 completed via card gateway'),
(NULL, 'payment', 'success', 'Payment webhook received: NP-019-CA $0.75 completed via M-Pesa STK Push'),
(NULL, 'payment', 'success', 'Payment webhook received: NP-001-JA $0.50 completed via M-Pesa STK Push'),
(NULL, 'payment', 'warning', 'Payment webhook retry: NP-030-TD gateway timeout — retrying (attempt 2/3)'),
(NULL, 'system', 'info', 'Platform payout batch processed — 4 vendors paid $22,847.50 total'),
(NULL, 'system', 'info', 'Platform commission settlement completed for period Aug 2026'),
('a1000000-0000-0000-0000-000000000002', 'router', 'error', 'Router MT-HOTEL-03 bandwidth spike detected — 95% utilization on Pool Deck'),
('a1000000-0000-0000-0000-000000000001', 'payment', 'success', 'Payment webhook received: NP-003-JC $0.50 completed via card gateway'),
('a1000000-0000-0000-0000-000000000003', 'heartbeat', 'success', 'Router MT-CAMPUS-02 heartbeat received — uptime 12d 5h 30m'),
(NULL, 'system', 'info', 'RADIUS auth log: 1,247 sessions authenticated in last hour'),
(NULL, 'system', 'warning', 'Gateway latency elevated — card processor avg response 850ms'),
('a1000000-0000-0000-0000-000000000004', 'system', 'info', 'Vendor Riverside Resort & Spa submitted onboarding documents'),
(NULL, 'system', 'success', 'Platform health check passed — all core services operational')
ON CONFLICT DO NOTHING;
