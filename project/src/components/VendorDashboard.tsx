import { useState, useEffect, useCallback, useRef } from 'react';
import { api } from '@/lib/api';
import { useTelemetry } from '@/hooks/useTelemetry';
import { useToast } from '@/components/Toast';
import Modal from '@/components/Modal';
import MetricCard from '@/components/MetricCard';
import StatusBadge from '@/components/StatusBadge';
import {
  formatCurrency, formatNumber, formatDuration, formatSpeed,
  timeAgo, formatDateTime, generateMacAddress, generateSecret,
} from '@/lib/utils';
import type { Tenant, Nas, HotspotPlan, Transaction, StaffMember, StaffRole } from '@/lib/types';
import {
  DollarSign, Wallet, Users, Router, Plus, Wifi,
  Copy, Check, Palette, Zap, Activity, RefreshCw,
  TrendingUp,
} from 'lucide-react';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';

interface VendorDashboardProps {
  tenant: Tenant;
  onBrandingChange: () => void;
}

export default function VendorDashboard({ tenant, onBrandingChange }: VendorDashboardProps) {
  const { toast } = useToast();
  const [routers, setRouters] = useState<Nas[]>([]);
  const [plans, setPlans] = useState<HotspotPlan[]>([]);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'overview' | 'routers' | 'plans' | 'transactions' | 'branding' | 'staff'>('overview');
  const [staff, setStaff] = useState<StaffMember[]>([]);
  const [staffForm, setStaffForm] = useState<{ email: string; password: string; role: StaffRole }>({ email: '', password: '', role: 'TECHNICIAN' });

  const [showRouterModal, setShowRouterModal] = useState(false);
  const [editingRouterId, setEditingRouterId] = useState<string | null>(null);
  const [showPlanModal, setShowPlanModal] = useState(false);
  const [editingPlan, setEditingPlan] = useState<HotspotPlan | null>(null);
  const [planError, setPlanError] = useState('');
  const [copiedScript, setCopiedScript] = useState(false);

  const [newRouter, setNewRouter] = useState({
    nasname: '',
    shortname: '',
    nas_ip: '10.10.0.10',
    api_port: '8728',
    api_username: 'admin',
    api_password: '',
    radius_server_ip: '10.10.0.5',
    shared_secret: '',
  });
  const [generatedMac, setGeneratedMac] = useState('');
  const [generatedSecret, setGeneratedSecret] = useState('');
  const [provisioningState, setProvisioningState] = useState<string>('idle');
  const [provisioningError, setProvisioningError] = useState('');
  const [provisioningBusy, setProvisioningBusy] = useState(false);
  const [refreshingRouters, setRefreshingRouters] = useState(false);

  const [planForm, setPlanForm] = useState({
    name: '', price: '', duration_minutes: '60', download_speed_kbps: '5120',
    upload_speed_kbps: '2048', simultaneous_devices: '1',
  });

  const [branding, setBranding] = useState({
    logo_url: tenant.logo_url,
    brand_color: tenant.brand_color,
    welcome_headline: tenant.welcome_headline,
    terms_of_service: tenant.terms_of_service,
  });
  const [savingBranding, setSavingBranding] = useState(false);
  const {
    telemetryData,
    trafficSamples,
    liveTelemetry,
    routerStats,
  } = useTelemetry(tenant.id);
  const telemetryOffline = Boolean(
    telemetryData
    && telemetryData.hotspot_status.total > 0
    && telemetryData.hotspot_status.active === 0,
  );

  const toastRef = useRef(toast);
  toastRef.current = toast;

  const fetchData = useCallback(async () => {
    try {
      const canManageStaff = !api.getAuthClaims()?.staff_role;
      const [routersData, plansData, transactionsData, staffData] = await Promise.all([
        api.getRouters(tenant.id),
        api.getPlans(tenant.id),
        api.getTransactions(tenant.id),
        canManageStaff ? api.getStaff() : Promise.resolve([]),
      ]);
      setRouters(routersData);
      setPlans(plansData);
      setTransactions(transactionsData);
      setStaff(staffData);
    } catch {
      toastRef.current('Unable to load vendor data', 'error');
    } finally {
      setLoading(false);
    }
  }, [tenant.id]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void (async () => {
      await fetchData();
      if (cancelled) return;
    })();
    return () => { cancelled = true; };
  }, [fetchData]);

  const refreshRouterStatuses = useCallback(async (notify = false) => {
    setRefreshingRouters(true);
    try {
      const currentRouters = await api.getRouters(tenant.id);
      setRouters(currentRouters);
      if (notify) toastRef.current('Router statuses refreshed');
    } catch {
      if (notify) toastRef.current('Unable to refresh router statuses', 'error');
    } finally {
      setRefreshingRouters(false);
    }
  }, [tenant.id]);

  useEffect(() => {
    setBranding({
      logo_url: tenant.logo_url,
      brand_color: tenant.brand_color,
      welcome_headline: tenant.welcome_headline,
      terms_of_service: tenant.terms_of_service,
    });
  }, [tenant]);

  const todayTx = transactions.filter((t) => {
    const d = new Date(t.created_at); const now = new Date();
    return d.getDate() === now.getDate() && d.getMonth() === now.getMonth();
  });
  const dailyGross = todayTx.reduce((s, t) => s + Number(t.gross_amount), 0);
  const monthlyGross = transactions.filter((t) => {
    const d = new Date(t.created_at); const now = new Date();
    return d.getMonth() === now.getMonth();
  }).reduce((s, t) => s + Number(t.gross_amount), 0);
  const netEarnings = transactions.reduce((s, t) => s + Number(t.vendor_net_amount), 0);
  const activeUsers = transactions.filter((t) => {
    return new Date(t.created_at).getTime() > Date.now() - 3600000;
  }).length;

  const revenueTrend = Array.from({ length: 14 }, (_, i) => {
    const date = new Date(); date.setDate(date.getDate() - (13 - i));
    const dayStr = date.toISOString().slice(0, 10);
    return {
      date: date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
      revenue: transactions.filter((t) => t.created_at.slice(0, 10) === dayStr).reduce((s, t) => s + Number(t.gross_amount), 0),
    };
  });
  const healthMetrics = telemetryData ? [
    { label: 'Server CPU', value: telemetryData.server_cpu },
    { label: 'MikroTik CPU', value: telemetryData.mikrotik_cpu },
    { label: 'Server memory', value: telemetryData.memory },
    { label: 'Server disk', value: telemetryData.disk },
    { label: 'Router memory', value: telemetryData.router_memory },
  ] : [];

  const handleAddRouter = async () => {
    if (!newRouter.nasname || !newRouter.shortname || !newRouter.nas_ip || !newRouter.api_username || !newRouter.api_password) {
      toast('Please fill in router name, location, router IP, and API credentials', 'error');
      return;
    }
    const apiPort = Number(newRouter.api_port);
    if (!Number.isInteger(apiPort) || apiPort < 1 || apiPort > 65535) {
      toast('API port must be a whole number between 1 and 65535.', 'error');
      return;
    }
    const mac = generatedMac || generateMacAddress();
    const secret = (newRouter.shared_secret || generatedSecret || generateSecret()).trim();
    setProvisioningBusy(true);
    setProvisioningState('Connecting to API...');
    setProvisioningError('');
    let provisionedRouterId: string | null = editingRouterId;
    try {
      const routerToProvision = editingRouterId
        ? await api.updateRouter(editingRouterId, {
          nasname: newRouter.nasname,
          shortname: newRouter.shortname,
          nas_ip: newRouter.nas_ip,
          api_port: apiPort,
          api_username: newRouter.api_username,
          api_password: newRouter.api_password,
          radius_server_ip: newRouter.radius_server_ip,
          shared_secret: secret,
          secret,
        })
        : await api.createRouter({
          tenant: tenant.id,
          nasname: newRouter.nasname,
          shortname: newRouter.shortname,
          nas_ip: newRouter.nas_ip,
          mac_address: mac,
          secret,
          api_port: apiPort,
          api_username: newRouter.api_username,
          api_password: newRouter.api_password,
          radius_server_ip: newRouter.radius_server_ip,
          shared_secret: secret,
          type: 'mikrotik',
        });
      provisionedRouterId = routerToProvision.id;

      setProvisioningState('Authenticating...');
      const response = await api.provisionRouter(routerToProvision.id, {
        api_ip: newRouter.nas_ip,
        api_port: apiPort,
        api_username: newRouter.api_username,
        api_password: newRouter.api_password,
        router_name: newRouter.nasname,
        venue: newRouter.shortname,
        radius_server_ip: newRouter.radius_server_ip,
        radius_ip: newRouter.radius_server_ip,
        secret,
        shared_secret: secret,
      });

      if (response.status !== 200) {
        throw new Error(response.data.message || 'Provisioning failed');
      }
      if (response.data.status !== 'success') {
        throw new Error(response.data.message || 'Provisioning failed');
      }

      setProvisioningState('Writing RADIUS & Hotspot Settings...');
      setProvisioningState('Syncing FreeRADIUS NAS...');
      setProvisioningState('Router Online!');
      toast(`Router "${newRouter.nasname}" was auto-provisioned successfully`);
      setNewRouter({ nasname: '', shortname: '', nas_ip: '10.10.0.10', api_port: '8728', api_username: 'admin', api_password: '', radius_server_ip: '10.10.0.5', shared_secret: '' });
      setGeneratedMac(''); setGeneratedSecret('');
      setShowRouterModal(false);
      setEditingRouterId(null);
    } catch (error: unknown) {
      if (provisionedRouterId) {
        setRouters((items) => items.map((router) => router.id === provisionedRouterId
          ? { ...router, is_online: false, status: 'offline' }
          : router));
      }
      const message = error instanceof Error ? error.message : 'Failed to add router';
      setProvisioningError(message.includes('Invalid Credentials') || message.includes('Authentication failed') || message.includes('credential') ? 'Invalid Credentials' : message.includes('port') || message.includes('unreachable') ? 'API Port Unreachable' : message.includes('failed') ? 'Authentication Failed' : message);
      setProvisioningState('Provisioning failed');
      toast(message, 'error');
    } finally {
      setProvisioningBusy(false);
      await fetchData();
    }
  };

  const closeRouterModal = () => {
    setShowRouterModal(false);
    void fetchData();
  };

  const mikrotikScript = (r: typeof newRouter, mac: string, secret: string) => `/radius add service=hotspot address=10.0.0.1 secret=${secret}
/radius add service=hotspot address=10.0.0.1 secret=${secret}
/ip hotspot profile set hsprof1 hotspot-address=10.0.0.1 use-radius=yes
/ip hotspot user profile set [find name=default] shared-users=1
/system identity set name=${r.nasname || 'MT-NEW'}
# MAC: ${mac}
# NAS IP: ${r.nas_ip || '10.0.0.1'}
# Location: ${r.shortname || 'New Location'}
# Generated by NetPulse SaaS`;

  const copyScript = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedScript(true);
    toast('MikroTik script copied to clipboard');
    setTimeout(() => setCopiedScript(false), 2000);
  };

  const handleSavePlan = async () => {
    setPlanError('');
    if (!planForm.name || !planForm.price) {
      setPlanError('Please fill in plan name and price.');
      return;
    }
    const price = parseFloat(planForm.price);
    const durationMinutes = parseInt(planForm.duration_minutes, 10);
    const downloadSpeedKbps = parseInt(planForm.download_speed_kbps, 10);
    const uploadSpeedKbps = parseInt(planForm.upload_speed_kbps, 10);
    const simultaneousDevices = parseInt(planForm.simultaneous_devices, 10);
    if (![price, durationMinutes, downloadSpeedKbps, uploadSpeedKbps, simultaneousDevices].every(Number.isFinite)) {
      setPlanError('Price, duration, bandwidth, and device values must be valid numbers.');
      return;
    }
    const payload = {
      tenant_id: tenant.id,
      name: planForm.name,
      price,
      duration_minutes: durationMinutes,
      download_speed_kbps: downloadSpeedKbps,
      upload_speed_kbps: uploadSpeedKbps,
      simultaneous_devices: simultaneousDevices,
      is_active: true,
    };
    if (editingPlan) {
      try { await api.updatePlan(editingPlan.id, payload); } catch (error) {
        setPlanError(error instanceof Error ? error.message : 'Failed to update plan.');
        return;
      }
      toast(`Plan "${planForm.name}" updated`);
    } else {
      try {
        const result = await api.createHotspotPlan({ ...payload, tenant: tenant.id });
        if (result.sync_warning) toast(result.sync_warning, 'error');
      } catch (err) {
        const error = err as Error & { response?: { data?: unknown } };
        console.error('400 Error Details:', error.response?.data);
        const details = formatPlanValidationErrors(error.response?.data);
        setPlanError(details || (error instanceof Error ? error.message : 'Failed to create plan.'));
        return;
      }
      toast(`Plan "${planForm.name}" created`);
    }
    setShowPlanModal(false);
    setPlanError('');
    setEditingPlan(null);
    setPlanForm({ name: '', price: '', duration_minutes: '60', download_speed_kbps: '5120', upload_speed_kbps: '2048', simultaneous_devices: '1' });
    fetchData();
  };

  const openEditPlan = (plan: HotspotPlan) => {
    setEditingPlan(plan);
    setPlanForm({
      name: plan.name, price: String(plan.price), duration_minutes: String(plan.duration_minutes),
      download_speed_kbps: String(plan.download_speed_kbps), upload_speed_kbps: String(plan.upload_speed_kbps),
      simultaneous_devices: String(plan.simultaneous_devices),
    });
    setShowPlanModal(true);
  };

  const togglePlanActive = async (plan: HotspotPlan) => {
    try { await api.updatePlan(plan.id, { is_active: !plan.is_active }); } catch { toast('Failed to update plan', 'error'); return; }
    toast(`Plan "${plan.name}" ${plan.is_active ? 'deactivated' : 'activated'}`);
    fetchData();
  };

  const handleSaveBranding = async () => {
    setSavingBranding(true);
    try { await api.updateTenant(tenant.id, {
      logo_url: branding.logo_url,
      brand_color: branding.brand_color,
      welcome_headline: branding.welcome_headline,
      terms_of_service: branding.terms_of_service,
    }); } catch { toast('Failed to save branding', 'error'); setSavingBranding(false); return; }
    toast('Portal branding updated successfully');
    setSavingBranding(false);
    onBrandingChange();
  };

  const inviteStaff = async () => {
    if (!staffForm.email || !staffForm.password) { toast('Enter a staff email and temporary password', 'error'); return; }
    try {
      const member = await api.inviteStaff(staffForm);
      setStaff((current) => [member, ...current]);
      setStaffForm({ email: '', password: '', role: 'TECHNICIAN' });
      toast('Staff member invited');
    } catch { toast('Unable to invite staff member', 'error'); }
  };

  const planNameById = (id: string | null) => plans.find((p) => p.id === id)?.name || '—';
  const nasNameById = (id: string | null) => routers.find((r) => r.id === id)?.nasname || '—';

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-white/20 border-t-indigo-500" />
      </div>
    );
  }

  const tabs = [
    { id: 'overview' as const, label: 'Overview', icon: Activity },
    { id: 'routers' as const, label: 'Router Fleet', icon: Router },
    { id: 'plans' as const, label: 'Hotspot Plans', icon: Wifi },
    { id: 'transactions' as const, label: 'Transactions', icon: DollarSign },
    { id: 'branding' as const, label: 'Portal Branding', icon: Palette },
    ...(!api.getAuthClaims()?.staff_role ? [{ id: 'staff' as const, label: 'Staff & Permissions', icon: Users }] : []),
  ];

  return (
    <div className="space-y-6">
      {/* Tabs */}
      <div className="flex flex-wrap gap-1 rounded-xl border border-white/10 bg-white/[0.02] p-1">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setActiveTab(t.id)}
            className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
              activeTab === t.id ? 'bg-white/10 text-white' : 'text-zinc-500 hover:text-zinc-300'
            }`}
          >
            <t.icon className="h-4 w-4" />
            {t.label}
          </button>
        ))}
      </div>

      {/* Overview Tab */}
      {activeTab === 'overview' && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <MetricCard label="Daily Gross Revenue" value={formatCurrency(dailyGross)} icon={<DollarSign className="h-5 w-5" />} accent="indigo" trend={`${todayTx.length} sales today`} trendUp />
            <MetricCard label="Monthly Gross" value={formatCurrency(monthlyGross)} icon={<Wallet className="h-5 w-5" />} accent="emerald" trend="+15.3% MoM" trendUp />
            <MetricCard label="Net Earnings" value={formatCurrency(netEarnings)} icon={<TrendingUp className="h-5 w-5" />} accent="amber" />
            <MetricCard label="Active Hotspot Users" value={formatNumber(activeUsers)} icon={<Users className="h-5 w-5" />} accent="sky" />
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <div className="glass-card rounded-2xl p-5 lg:col-span-2">
              <h3 className="mb-4 text-sm font-semibold text-white">Revenue Trend</h3>
              <ResponsiveContainer width="100%" height={240}>
                <AreaChart data={revenueTrend}>
                  <defs>
                    <linearGradient id="vRev" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                  <XAxis dataKey="date" tick={{ fill: '#71717a', fontSize: 11 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill: '#71717a', fontSize: 11 }} axisLine={false} tickLine={false} />
                  <Tooltip contentStyle={{ background: '#18181b', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '12px', fontSize: '12px' }} formatter={(v: number) => formatCurrency(v)} />
                  <Area type="monotone" dataKey="revenue" stroke="#6366f1" strokeWidth={2} fill="url(#vRev)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>

            <div className="glass-card rounded-2xl p-5">
              <div className="mb-4 flex items-center justify-between">
                <h3 className="text-sm font-semibold text-white">Router Status</h3>
                <Router className="h-5 w-5 text-violet-400" />
              </div>
              <div className="space-y-3">
                <div className="flex items-center justify-between rounded-xl border border-emerald-500/20 bg-emerald-500/5 px-4 py-3">
                  <div className="flex items-center gap-3">
                    <div className="h-2.5 w-2.5 rounded-full bg-emerald-400 animate-pulse" />
                    <span className="text-sm font-medium text-white">Online</span>
                  </div>
                  <span className="text-xl font-bold text-emerald-400">{routerStats.online_routers}</span>
                </div>
                <div className="flex items-center justify-between rounded-xl border border-zinc-500/20 bg-zinc-500/5 px-4 py-3">
                  <div className="flex items-center gap-3">
                    <div className="h-2.5 w-2.5 rounded-full bg-zinc-500" />
                    <span className="text-sm font-medium text-white">Offline</span>
                  </div>
                    <span className="text-xl font-bold text-zinc-400">{routerStats.offline_routers}</span>
                </div>
                <div className="rounded-xl border border-white/5 bg-white/[0.02] px-4 py-3">
                  <div className="flex items-center justify-between text-xs text-zinc-400">
                    <span>Total Routers</span>
                    <span className="font-semibold text-white">{routerStats.total_routers}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-[0.9fr_1.1fr]">
            <div className="glass-card rounded-2xl p-5">
              <h3 className="mb-4 text-sm font-semibold text-white">Router &amp; server health</h3>
              <div className="space-y-3">
                {healthMetrics.map(({ label, value }) => (
                  <div key={label}>
                    <div className="mb-1 flex justify-between text-xs text-zinc-400"><span>{label}</span><span>{value.toFixed(1)}%</span></div>
                    <div className="h-2 rounded-full bg-white/10"><div className="h-full rounded-full bg-cyan-300 transition-all" style={{ width: `${Math.min(100, Math.max(0, value))}%` }} /></div>
                  </div>
                ))}
              </div>
            </div>
            <div className="glass-card rounded-2xl p-5">
              <div className="mb-4 flex items-center justify-between"><h3 className="text-sm font-semibold text-white">Live network traffic</h3><Activity className="h-5 w-5 text-cyan-300" /></div>
              <ResponsiveContainer width="100%" height={170}>
                <AreaChart data={trafficSamples.map((sample) => ({ ...sample, time: new Date(sample.timestamp).toLocaleTimeString([], { minute: '2-digit', second: '2-digit' }) }))}>
                  <CartesianGrid stroke="rgba(255,255,255,.06)" /><XAxis dataKey="time" tick={{ fill: '#71717a', fontSize: 10 }} /><YAxis tick={{ fill: '#71717a', fontSize: 10 }} /><Tooltip contentStyle={{ background: '#10252a', border: '1px solid rgba(255,255,255,.1)' }} />
                  <Area dataKey="tx_kbps" stroke="#2dd4bf" fill="#2dd4bf" fillOpacity={0.15} /><Area dataKey="rx_kbps" stroke="#38bdf8" fill="#38bdf8" fillOpacity={0.15} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="glass-card rounded-2xl p-5">
            <div className="flex items-start justify-between">
              <div>
                <h3 className="text-sm font-semibold text-white">Network telemetry</h3>
                <p className="mt-1 text-xs text-zinc-500">Live bandwidth data from your router fleet</p>
              </div>
              <Activity className="h-5 w-5 text-cyan-300" />
            </div>
            {telemetryOffline ? (
              <div className="mt-6 rounded-xl border border-dashed border-rose-300/20 bg-rose-300/[0.04] px-5 py-7 text-center">
                <p className="text-sm font-medium text-white">Router Offline - Telemetry Stream Paused</p>
                <p className="mx-auto mt-1 max-w-xs text-xs leading-relaxed text-zinc-500">Re-connect or power on the router to resume live tracking.</p>
              </div>
            ) : liveTelemetry ? (
              <div className="mt-6 grid grid-cols-3 gap-3">
                <div className="rounded-xl border border-cyan-300/20 bg-cyan-300/[0.04] p-4"><p className="text-xs text-zinc-500">RX bytes</p><p className="mt-2 text-lg font-semibold text-cyan-200">{formatBytes(liveTelemetry.rx_bytes)}</p></div>
                <div className="rounded-xl border border-emerald-300/20 bg-emerald-300/[0.04] p-4"><p className="text-xs text-zinc-500">TX bytes</p><p className="mt-2 text-lg font-semibold text-emerald-200">{formatBytes(liveTelemetry.tx_bytes)}</p></div>
                <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4"><p className="text-xs text-zinc-500">Interface</p><p className="mt-2 truncate text-lg font-semibold text-white">{liveTelemetry.interface}</p></div>
              </div>
            ) : (
              <div className="mt-6 rounded-xl border border-dashed border-cyan-300/20 bg-cyan-300/[0.04] px-5 py-7 text-center">
                <p className="text-sm font-medium text-white">Waiting for router telemetry</p>
                <p className="mx-auto mt-1 max-w-xs text-xs leading-relaxed text-zinc-500">Connect a router heartbeat to unlock live throughput, latency, and usage trends.</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Router Fleet Tab */}
      {activeTab === 'routers' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-white">Router Fleet ({routers.length})</h3>
            <div className="flex items-center gap-2">
              <button
                onClick={() => { void refreshRouterStatuses(true); }}
                disabled={refreshingRouters}
                className="flex items-center gap-1.5 rounded-lg border border-white/10 px-3 py-2 text-xs font-medium text-zinc-300 hover:bg-white/5 disabled:opacity-50 transition-colors"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${refreshingRouters ? 'animate-spin' : ''}`} /> Refresh Status
              </button>
              <button
                onClick={() => { setGeneratedMac(generateMacAddress()); setGeneratedSecret(generateSecret()); setShowRouterModal(true); }}
                className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-2 text-xs font-medium text-white hover:bg-indigo-500 transition-colors"
              >
                <Plus className="h-3.5 w-3.5" /> Add New Router
              </button>
            </div>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {routers.map((r) => (
              <div key={r.id} className="glass-card glass-card-hover rounded-2xl p-4">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className={`flex h-10 w-10 items-center justify-center rounded-xl ${r.is_online ? 'bg-emerald-500/15 text-emerald-400' : 'bg-zinc-500/15 text-zinc-500'}`}>
                      <Router className="h-5 w-5" />
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-white">{r.nasname}</p>
                      <p className="text-xs text-zinc-500">{r.shortname}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <StatusBadge status={r.status || (r.is_online ? 'online' : 'offline')} />
                    <button onClick={() => { setEditingRouterId(r.id); setNewRouter({ nasname: r.nasname, shortname: r.shortname, nas_ip: r.nas_ip, api_port: String((r as Nas & { api_port?: number }).api_port || 8728), api_username: (r as Nas & { api_username?: string }).api_username || 'admin', api_password: '', radius_server_ip: (r as Nas & { radius_server_ip?: string }).radius_server_ip || '10.10.0.5', shared_secret: '' }); setShowRouterModal(true); }} className="text-xs text-indigo-300 hover:text-indigo-200">Edit</button>
                  </div>
                </div>
                <div className="mt-4 space-y-2 text-xs">
                  <div className="flex justify-between">
                    <span className="text-zinc-500">MAC Address</span>
                    <span className="font-mono text-zinc-300">{r.mac_address}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-zinc-500">NAS IP</span>
                    <span className="font-mono text-zinc-300">{r.nas_ip}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-zinc-500">Shared Secret</span>
                    <span className="font-mono text-zinc-300">{r.secret}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-zinc-500">Last Ping</span>
                    <span className="text-zinc-400">{r.is_online ? timeAgo(r.last_ping) : 'offline'}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Hotspot Plans Tab */}
      {activeTab === 'plans' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-white">Hotspot Plans ({plans.length})</h3>
            <button
              onClick={() => { setEditingPlan(null); setPlanForm({ name: '', price: '', duration_minutes: '60', download_speed_kbps: '5120', upload_speed_kbps: '2048', simultaneous_devices: '1' }); setShowPlanModal(true); }}
              className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-2 text-xs font-medium text-white hover:bg-indigo-500 transition-colors"
            >
              <Plus className="h-3.5 w-3.5" /> Create Plan
            </button>
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {plans.map((p) => (
              <div key={p.id} className={`glass-card glass-card-hover rounded-2xl p-5 ${!p.is_active ? 'opacity-50' : ''}`}>
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-2">
                    <div className="rounded-lg bg-indigo-500/15 p-2">
                      <Wifi className="h-4 w-4 text-indigo-400" />
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-white">{p.name}</p>
                      <p className="text-xs text-zinc-500">{formatDuration(p.duration_minutes)}</p>
                    </div>
                  </div>
                  <span className={`rounded-full border px-2 py-0.5 text-xs ${p.is_active ? 'border-emerald-500/20 bg-emerald-500/10 text-emerald-300' : 'border-zinc-500/20 bg-zinc-500/10 text-zinc-400'}`}>
                    {p.is_active ? 'Active' : 'Inactive'}
                  </span>
                </div>
                <div className="mt-4">
                  <p className="text-2xl font-bold text-white">{formatCurrency(p.price)}</p>
                </div>
                <div className="mt-4 grid grid-cols-2 gap-2 text-xs">
                  <div className="rounded-lg border border-white/5 bg-white/[0.02] px-3 py-2">
                    <p className="text-zinc-500">Download</p>
                    <p className="font-medium text-zinc-300">{formatSpeed(p.download_speed_kbps)}</p>
                  </div>
                  <div className="rounded-lg border border-white/5 bg-white/[0.02] px-3 py-2">
                    <p className="text-zinc-500">Upload</p>
                    <p className="font-medium text-zinc-300">{formatSpeed(p.upload_speed_kbps)}</p>
                  </div>
                  <div className="rounded-lg border border-white/5 bg-white/[0.02] px-3 py-2">
                    <p className="text-zinc-500">Devices</p>
                    <p className="font-medium text-zinc-300">{p.simultaneous_devices}</p>
                  </div>
                  <div className="rounded-lg border border-white/5 bg-white/[0.02] px-3 py-2">
                    <p className="text-zinc-500">Duration</p>
                    <p className="font-medium text-zinc-300">{formatDuration(p.duration_minutes)}</p>
                  </div>
                </div>
                <div className="mt-4 flex items-center gap-2">
                  <button onClick={() => openEditPlan(p)} className="flex-1 rounded-lg border border-white/10 px-3 py-2 text-xs font-medium text-zinc-300 hover:bg-white/5 transition-colors">Edit</button>
                  <button onClick={() => togglePlanActive(p)} className="flex-1 rounded-lg border border-white/10 px-3 py-2 text-xs font-medium text-zinc-300 hover:bg-white/5 transition-colors">{p.is_active ? 'Deactivate' : 'Activate'}</button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Transactions Tab */}
      {activeTab === 'transactions' && (
        <div className="glass-card rounded-2xl overflow-hidden">
          <div className="border-b border-white/10 px-5 py-4">
            <h3 className="text-sm font-semibold text-white">Transaction Ledger ({transactions.length})</h3>
            <p className="text-xs text-zinc-500">All customer payments for {tenant.business_name}</p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-white/10 text-left text-xs text-zinc-500">
                  <th className="px-5 py-3 font-medium">Payment Ref</th>
                  <th className="px-5 py-3 font-medium">Customer</th>
                  <th className="px-5 py-3 font-medium">Package</th>
                  <th className="px-5 py-3 font-medium">Router</th>
                  <th className="px-5 py-3 font-medium">Gross Paid</th>
                  <th className="px-5 py-3 font-medium">Commission</th>
                  <th className="px-5 py-3 font-medium">Net Balance</th>
                  <th className="px-5 py-3 font-medium">Method</th>
                  <th className="px-5 py-3 font-medium">Date</th>
                </tr>
              </thead>
              <tbody>
                {transactions.map((t) => (
                  <tr key={t.id} className="border-b border-white/5 hover:bg-white/[0.02] transition-colors">
                    <td className="px-5 py-3.5"><span className="font-mono text-xs text-indigo-300">{t.payment_ref}</span></td>
                    <td className="px-5 py-3.5">
                      <p className="text-xs text-zinc-300">{t.customer_phone}</p>
                      <p className="font-mono text-[10px] text-zinc-600">{t.customer_mac}</p>
                    </td>
                    <td className="px-5 py-3.5 text-zinc-300">{planNameById(t.plan_id)}</td>
                    <td className="px-5 py-3.5 text-zinc-400">{nasNameById(t.nas_id)}</td>
                    <td className="px-5 py-3.5 font-medium text-white">{formatCurrency(Number(t.gross_amount))}</td>
                    <td className="px-5 py-3.5 text-rose-400">-{formatCurrency(Number(t.platform_fee))}</td>
                    <td className="px-5 py-3.5 font-medium text-emerald-400">{formatCurrency(Number(t.vendor_net_amount))}</td>
                    <td className="px-5 py-3.5">
                      <span className="rounded-md bg-white/5 px-2 py-1 text-xs capitalize text-zinc-300">{t.payment_method.replace('_', ' ')}</span>
                    </td>
                    <td className="px-5 py-3.5 text-xs text-zinc-500">{formatDateTime(t.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Branding Tab */}
      {activeTab === 'branding' && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <div className="glass-card rounded-2xl p-6">
            <h3 className="mb-5 text-sm font-semibold text-white">Portal Branding Customizer</h3>
            <div className="space-y-4">
              <div>
                <label className="mb-1.5 block text-xs font-medium text-zinc-400">Logo URL</label>
                <div className="flex gap-2">
                  <input
                    value={branding.logo_url}
                    onChange={(e) => setBranding({ ...branding, logo_url: e.target.value })}
                    placeholder="https://example.com/logo.png"
                    className="flex-1 rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white placeholder-zinc-600 focus:border-indigo-500/50 focus:outline-none focus:ring-1 focus:ring-indigo-500/30"
                  />
                </div>
              </div>
              <div>
                <label className="mb-1.5 block text-xs font-medium text-zinc-400">Brand Color</label>
                <div className="flex items-center gap-3">
                  <input
                    type="color"
                    value={branding.brand_color}
                    onChange={(e) => setBranding({ ...branding, brand_color: e.target.value })}
                    className="h-10 w-16 cursor-pointer rounded-lg border border-white/10 bg-transparent"
                  />
                  <input
                    value={branding.brand_color}
                    onChange={(e) => setBranding({ ...branding, brand_color: e.target.value })}
                    className="flex-1 rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm font-mono text-white focus:border-indigo-500/50 focus:outline-none focus:ring-1 focus:ring-indigo-500/30"
                  />
                </div>
              </div>
              <div>
                <label className="mb-1.5 block text-xs font-medium text-zinc-400">Welcome Headline</label>
                <input
                  value={branding.welcome_headline}
                  onChange={(e) => setBranding({ ...branding, welcome_headline: e.target.value })}
                  className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white focus:border-indigo-500/50 focus:outline-none focus:ring-1 focus:ring-indigo-500/30"
                />
              </div>
              <div>
                <label className="mb-1.5 block text-xs font-medium text-zinc-400">Terms of Service</label>
                <textarea
                  value={branding.terms_of_service}
                  onChange={(e) => setBranding({ ...branding, terms_of_service: e.target.value })}
                  rows={4}
                  className="w-full resize-none rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white focus:border-indigo-500/50 focus:outline-none focus:ring-1 focus:ring-indigo-500/30"
                />
              </div>
              <button
                onClick={handleSaveBranding}
                disabled={savingBranding}
                className="flex w-full items-center justify-center gap-2 rounded-xl bg-indigo-600 px-4 py-3 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50 transition-colors"
              >
                {savingBranding ? <div className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" /> : <><Palette className="h-4 w-4" /> Save Branding</>}
              </button>
            </div>
          </div>

          <div className="glass-card rounded-2xl p-6">
            <h3 className="mb-5 text-sm font-semibold text-white">Live Portal Preview</h3>
            <div className="rounded-2xl border border-white/10 p-6" style={{ background: `linear-gradient(135deg, ${branding.brand_color}15, #0a0a0b)` }}>
              {branding.logo_url ? (
                <img src={branding.logo_url} alt="Logo" className="mb-4 h-16 w-16 rounded-xl object-cover" />
              ) : (
                <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-xl text-2xl font-bold text-white" style={{ background: branding.brand_color }}>
                  {tenant.business_name.charAt(0)}
                </div>
              )}
              <h4 className="text-lg font-bold text-white">{branding.welcome_headline || 'Welcome'}</h4>
              <p className="mt-2 text-sm text-zinc-400">{tenant.business_name}</p>
              <div className="mt-4 space-y-2">
                {plans.filter((p) => p.is_active).slice(0, 3).map((p) => (
                  <div key={p.id} className="flex items-center justify-between rounded-xl border border-white/10 bg-white/5 px-4 py-3">
                    <div>
                      <p className="text-sm font-medium text-white">{p.name}</p>
                      <p className="text-xs text-zinc-500">{formatDuration(p.duration_minutes)}</p>
                    </div>
                    <span className="font-bold text-white" style={{ color: branding.brand_color }}>{formatCurrency(p.price)}</span>
                  </div>
                ))}
              </div>
              <p className="mt-4 text-xs text-zinc-600">{branding.terms_of_service}</p>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'staff' && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[0.8fr_1.2fr]">
          <div className="glass-card rounded-2xl p-6">
            <h3 className="text-sm font-semibold text-white">Invite staff member</h3>
            <p className="mt-1 text-xs text-zinc-500">Staff access is limited to this vendor account.</p>
            <div className="mt-5 space-y-3">
              <input value={staffForm.email} onChange={(e) => setStaffForm({ ...staffForm, email: e.target.value })} type="email" placeholder="staff@business.com" className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white" />
              <input value={staffForm.password} onChange={(e) => setStaffForm({ ...staffForm, password: e.target.value })} type="password" placeholder="Temporary password" className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white" />
              <select value={staffForm.role} onChange={(e) => setStaffForm({ ...staffForm, role: e.target.value as StaffRole })} className="w-full rounded-xl border border-white/10 bg-zinc-900 px-4 py-2.5 text-sm text-white">
                <option value="MANAGER">Manager · routers and plans</option>
                <option value="TECHNICIAN">Technician · router monitoring</option>
                <option value="CASHIER">Cashier · customer sales</option>
              </select>
              <button onClick={inviteStaff} className="w-full rounded-xl bg-indigo-600 px-4 py-3 text-sm font-medium text-white hover:bg-indigo-500">Invite staff</button>
            </div>
          </div>
          <div className="glass-card overflow-hidden rounded-2xl">
            <div className="border-b border-white/10 px-5 py-4"><h3 className="text-sm font-semibold text-white">Permission roster</h3><p className="text-xs text-zinc-500">Change role access without changing ownership.</p></div>
            <div className="divide-y divide-white/5">
              {staff.map((member) => <div key={member.id} className="flex items-center justify-between gap-4 px-5 py-4">
                <div><p className="text-sm font-medium text-white">{member.email}</p><p className="text-xs text-zinc-500">{member.is_active ? 'Active' : 'Disabled'}</p></div>
                <select value={member.role} onChange={async (e) => { const updated = await api.updateStaff(member.id, { role: e.target.value as StaffRole }); setStaff((current) => current.map((item) => item.id === updated.id ? updated : item)); }} className="rounded-lg border border-white/10 bg-zinc-900 px-3 py-2 text-xs text-white">
                  <option value="MANAGER">Manager</option><option value="TECHNICIAN">Technician</option><option value="CASHIER">Cashier</option>
                </select>
              </div>)}
              {staff.length === 0 && <p className="px-5 py-8 text-sm text-zinc-500">No staff members invited yet.</p>}
            </div>
          </div>
        </div>
      )}

      {/* Add Router Modal */}
      <Modal
        open={showRouterModal}
        onClose={closeRouterModal}
        title={editingRouterId ? 'Edit Router' : 'Add New Router'}
        description={editingRouterId ? 'Update credentials and reprovision this MikroTik NAS' : 'Register a new MikroTik NAS to your fleet'}
        size="lg"
        footer={
          <>
            <button onClick={closeRouterModal} className="rounded-lg border border-white/10 px-4 py-2 text-sm text-zinc-300 hover:bg-white/5 transition-colors">Cancel</button>
            <button onClick={handleAddRouter} disabled={provisioningBusy} className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-60 transition-colors">
              {provisioningBusy ? 'Provisioning...' : 'Test Connection & Auto-Provision'}
            </button>
          </>
        }
      >
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="mb-1.5 block text-xs font-medium text-zinc-400">Router Name (NAS Name)</label>
              <input
                value={newRouter.nasname}
                onChange={(e) => setNewRouter({ ...newRouter, nasname: e.target.value })}
                placeholder="MT-CAFE-03"
                className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white placeholder-zinc-600 focus:border-indigo-500/50 focus:outline-none focus:ring-1 focus:ring-indigo-500/30"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium text-zinc-400">Venue Location</label>
              <input
                value={newRouter.shortname}
                onChange={(e) => setNewRouter({ ...newRouter, shortname: e.target.value })}
                placeholder="Main Cafe"
                className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white placeholder-zinc-600 focus:border-indigo-500/50 focus:outline-none focus:ring-1 focus:ring-indigo-500/30"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="mb-1.5 block text-xs font-medium text-zinc-400">Router IP Address</label>
              <input
                value={newRouter.nas_ip}
                onChange={(e) => setNewRouter({ ...newRouter, nas_ip: e.target.value })}
                placeholder="10.10.1.3"
                className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white placeholder-zinc-600 focus:border-indigo-500/50 focus:outline-none focus:ring-1 focus:ring-indigo-500/30"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium text-zinc-400">API Port</label>
              <input
                value={newRouter.api_port}
                onChange={(e) => setNewRouter({ ...newRouter, api_port: e.target.value })}
                placeholder="8728"
                className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white focus:border-indigo-500/50 focus:outline-none focus:ring-1 focus:ring-indigo-500/30"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="mb-1.5 block text-xs font-medium text-zinc-400">API Username</label>
              <input
                value={newRouter.api_username}
                onChange={(e) => setNewRouter({ ...newRouter, api_username: e.target.value })}
                placeholder="billing_api"
                className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white placeholder-zinc-600 focus:border-indigo-500/50 focus:outline-none focus:ring-1 focus:ring-indigo-500/30"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium text-zinc-400">API Password</label>
              <input
                type="password"
                value={newRouter.api_password}
                onChange={(e) => setNewRouter({ ...newRouter, api_password: e.target.value })}
                placeholder="••••••••"
                className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white focus:border-indigo-500/50 focus:outline-none focus:ring-1 focus:ring-indigo-500/30"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="mb-1.5 block text-xs font-medium text-zinc-400">RADIUS Server IP</label>
              <input
                value={newRouter.radius_server_ip}
                onChange={(e) => setNewRouter({ ...newRouter, radius_server_ip: e.target.value })}
                placeholder="10.10.0.5"
                className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white placeholder-zinc-600 focus:border-indigo-500/50 focus:outline-none focus:ring-1 focus:ring-indigo-500/30"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium text-zinc-400">RADIUS Shared Secret</label>
              <input
                value={newRouter.shared_secret || generatedSecret}
                onChange={(e) => {
                  setNewRouter({ ...newRouter, shared_secret: e.target.value });
                  setGeneratedSecret(e.target.value);
                }}
                className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm font-mono text-white focus:border-indigo-500/50 focus:outline-none focus:ring-1 focus:ring-indigo-500/30"
              />
            </div>
          </div>

          <div className="rounded-xl border border-indigo-500/20 bg-indigo-500/5 px-4 py-3">
            <div className="mb-2 flex items-center justify-between text-xs font-medium text-zinc-300">
              <span>Provisioning status</span>
              <span className="text-indigo-300">{provisioningState}</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-white/5">
              <div className={`h-full rounded-full transition-all ${provisioningState === 'Router Online!' ? 'w-full bg-emerald-500' : 'w-2/3 bg-indigo-500'}`} />
            </div>
            {provisioningError && <p className="mt-2 text-xs text-rose-300">{provisioningError}</p>}
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="mb-1.5 block text-xs font-medium text-zinc-400">MAC Address (auto-generated)</label>
              <div className="flex gap-2">
                <input
                  value={generatedMac}
                  onChange={(e) => setGeneratedMac(e.target.value)}
                  className="flex-1 rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm font-mono text-white focus:border-indigo-500/50 focus:outline-none focus:ring-1 focus:ring-indigo-500/30"
                />
                <button onClick={() => setGeneratedMac(generateMacAddress())} className="rounded-xl border border-white/10 px-3 text-zinc-400 hover:bg-white/5 transition-colors">
                  <Zap className="h-4 w-4" />
                </button>
              </div>
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium text-zinc-400">Shared Secret</label>
              <div className="flex gap-2">
                <input
                  value={generatedSecret}
                  onChange={(e) => setGeneratedSecret(e.target.value)}
                  className="flex-1 rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm font-mono text-white focus:border-indigo-500/50 focus:outline-none focus:ring-1 focus:ring-indigo-500/30"
                />
                <button onClick={() => setGeneratedSecret(generateSecret())} className="rounded-xl border border-white/10 px-3 text-zinc-400 hover:bg-white/5 transition-colors">
                  <Zap className="h-4 w-4" />
                </button>
              </div>
            </div>
          </div>

          <div>
            <label className="mb-1.5 block text-xs font-medium text-zinc-400">MikroTik Auto-Configuration Script</label>
            <div className="relative">
              <pre className="max-h-48 overflow-auto rounded-xl border border-white/10 bg-black/40 p-4 text-xs font-mono text-emerald-300 leading-relaxed">
                {mikrotikScript(newRouter, generatedMac, generatedSecret)}
              </pre>
              <button
                onClick={() => copyScript(mikrotikScript(newRouter, generatedMac, generatedSecret))}
                className="absolute right-3 top-3 rounded-lg border border-white/10 bg-zinc-900/80 px-2.5 py-1.5 text-xs font-medium text-zinc-300 hover:bg-white/10 transition-colors"
              >
                {copiedScript ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
                <span className="ml-1">{copiedScript ? 'Copied' : 'Copy'}</span>
              </button>
            </div>
            <p className="mt-2 text-xs text-zinc-600">Paste this script into your MikroTik terminal to auto-configure RADIUS authentication</p>
          </div>
        </div>
      </Modal>

      {/* Plan Modal */}
      <Modal
        open={showPlanModal}
        onClose={() => setShowPlanModal(false)}
        title={editingPlan ? 'Edit Hotspot Plan' : 'Create Hotspot Plan'}
        description="Configure Wi-Fi package details"
        footer={
          <>
            <button onClick={() => setShowPlanModal(false)} className="rounded-lg border border-white/10 px-4 py-2 text-sm text-zinc-300 hover:bg-white/5 transition-colors">Cancel</button>
            <button onClick={handleSavePlan} className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 transition-colors">{editingPlan ? 'Update Plan' : 'Create Plan'}</button>
          </>
        }
      >
        <div className="space-y-4">
          <div>
            <label className="mb-1.5 block text-xs font-medium text-zinc-400">Package Name</label>
            <input
              value={planForm.name}
              onChange={(e) => setPlanForm({ ...planForm, name: e.target.value })}
              placeholder="e.g. 1 Hour Speed Boost"
              className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white placeholder-zinc-600 focus:border-indigo-500/50 focus:outline-none focus:ring-1 focus:ring-indigo-500/30"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="mb-1.5 block text-xs font-medium text-zinc-400">Price (KES)</label>
              <input
                type="number" step="0.01" value={planForm.price}
                onChange={(e) => setPlanForm({ ...planForm, price: e.target.value })}
                placeholder="50"
                className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white focus:border-indigo-500/50 focus:outline-none focus:ring-1 focus:ring-indigo-500/30"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium text-zinc-400">Duration (minutes)</label>
              <input
                type="number" value={planForm.duration_minutes}
                onChange={(e) => setPlanForm({ ...planForm, duration_minutes: e.target.value })}
                className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white focus:border-indigo-500/50 focus:outline-none focus:ring-1 focus:ring-indigo-500/30"
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="mb-1.5 block text-xs font-medium text-zinc-400">Download Speed (Kbps)</label>
              <input
                type="number" value={planForm.download_speed_kbps}
                onChange={(e) => setPlanForm({ ...planForm, download_speed_kbps: e.target.value })}
                className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white focus:border-indigo-500/50 focus:outline-none focus:ring-1 focus:ring-indigo-500/30"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium text-zinc-400">Upload Speed (Kbps)</label>
              <input
                type="number" value={planForm.upload_speed_kbps}
                onChange={(e) => setPlanForm({ ...planForm, upload_speed_kbps: e.target.value })}
                className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white focus:border-indigo-500/50 focus:outline-none focus:ring-1 focus:ring-indigo-500/30"
              />
            </div>
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-medium text-zinc-400">Simultaneous Devices</label>
            <input
              type="number" min="1" max="10" value={planForm.simultaneous_devices}
              onChange={(e) => setPlanForm({ ...planForm, simultaneous_devices: e.target.value })}
              className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white focus:border-indigo-500/50 focus:outline-none focus:ring-1 focus:ring-indigo-500/30"
            />
          </div>
          {planError && <p className="rounded-lg border border-rose-400/30 bg-rose-400/10 px-3 py-2 text-sm text-rose-300">{planError}</p>}
        </div>
      </Modal>
    </div>
  );
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KB`;
  if (value < 1024 ** 3) return `${(value / 1024 ** 2).toFixed(1)} MB`;
  return `${(value / 1024 ** 3).toFixed(1)} GB`;
}

function formatPlanValidationErrors(data: unknown): string {
  if (Array.isArray(data)) return data.map((item) => String(item)).join(' ');
  if (!data || typeof data !== 'object') return '';
  return Object.entries(data as Record<string, unknown>)
    .map(([field, value]) => {
      const message = Array.isArray(value) ? value.join(', ') : typeof value === 'object' && value !== null ? JSON.stringify(value) : String(value);
      return `${field}: ${message}`;
    })
    .join(' ');
}
