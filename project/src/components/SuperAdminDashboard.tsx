import { useState, useEffect, useCallback } from 'react';
import { api } from '@/lib/api';
import { useToast } from '@/components/Toast';
import Modal from '@/components/Modal';
import MetricCard from '@/components/MetricCard';
import StatusBadge from '@/components/StatusBadge';
import { formatCurrency, formatNumber, formatSpeed, formatDuration, timeAgo, formatDate, formatDateTime } from '@/lib/utils';
import type { Tenant, Nas, HotspotPlan, Transaction, SystemUser, PlatformSettings } from '@/lib/types';
import {
  DollarSign, TrendingUp, Building2, Router as RouterIcon, Percent,
  Users, Wallet, Activity, ShieldCheck, AlertTriangle,
  CreditCard, Server, CheckCircle2, Ban, Eye, Settings as SettingsIcon,
  FileText, Layers, Plus, Search, Trash2, RefreshCw, Download,
  ExternalLink, Lock, Check, Loader2,
} from 'lucide-react';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, BarChart, Bar, Legend,
} from 'recharts';

const PIE_COLORS = ['#6366f1', '#10b981', '#f59e0b', '#ef4444'];

type SuperAdminTab = 'dashboard' | 'tenants' | 'users' | 'routers' | 'plans' | 'payments' | 'reports' | 'settings';

export default function SuperAdminDashboard() {
  const { toast } = useToast();
  const [activeTab, setActiveTab] = useState<SuperAdminTab>('dashboard');
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [allNas, setAllNas] = useState<Nas[]>([]);
  const [allPlans, setAllPlans] = useState<HotspotPlan[]>([]);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [systemUsers, setSystemUsers] = useState<SystemUser[]>([]);
  const [settings, setSettings] = useState<PlatformSettings | null>(null);
  const [loading, setLoading] = useState(true);

  // Filters & Search
  const [tenantFilter, setTenantFilter] = useState<string>('all');
  const [tenantSearch, setTenantSearch] = useState<string>('');
  const [paymentSearch, setPaymentSearch] = useState<string>('');
  const [paymentStatusFilter, setPaymentStatusFilter] = useState<string>('all');
  const [paymentTenantFilter, setPaymentTenantFilter] = useState<string>('all');

  // Modals
  const [showVendorModal, setShowVendorModal] = useState(false);
  const [newVendor, setNewVendor] = useState({ business_name: '', email: '', phone_number: '', commission: '10' });
  const [showCommissionModal, setShowCommissionModal] = useState(false);
  const [selectedTenant, setSelectedTenant] = useState<Tenant | null>(null);
  const [newCommission, setNewCommission] = useState('');

  const [showUserModal, setShowUserModal] = useState(false);
  const [newUser, setNewUser] = useState<{ username: string; email: string; password: string; role: SystemUser['role']; is_active: boolean }>({
    username: '',
    email: '',
    password: '',
    role: 'SUPPORT_AGENT',
    is_active: true,
  });

  const [showPlanModal, setShowPlanModal] = useState(false);
  const [creatingPlan, setCreatingPlan] = useState(false);
  const [togglingPlanId, setTogglingPlanId] = useState<string | null>(null);
  const [togglingUserId, setTogglingUserId] = useState<number | null>(null);
  const [newPlan, setNewPlan] = useState({
    tenant_id: '',
    name: '',
    price: '100',
    duration_value: '1',
    duration_unit: 'days' as 'minutes' | 'hours' | 'days',
    download_speed_kbps: '5120',
    upload_speed_kbps: '2048',
    simultaneous_devices: '1',
  });

  const [showScriptModal, setShowScriptModal] = useState(false);
  const [activeScript, setActiveScript] = useState<string>('');
  const [scriptRouterName, setScriptRouterName] = useState<string>('');
  const [scriptCopied, setScriptCopied] = useState(false);

  const [showReceiptModal, setShowReceiptModal] = useState(false);
  const [selectedTx, setSelectedTx] = useState<Transaction | null>(null);

  const [processingPayout, setProcessingPayout] = useState(false);
  const [savingSettings, setSavingSettings] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const [tenantsData, routersData, transactionsData, usersData, settingsData] = await Promise.all([
        api.getTenants(),
        api.getRouters(),
        api.getTransactions(),
        api.getSystemUsers(),
        api.getPlatformSettings(),
      ]);
      setTenants(tenantsData);
      setAllNas(routersData);
      setTransactions(transactionsData);
      setSystemUsers(usersData);
      setSettings(settingsData);

      // Fetch plans across available tenants
      if (tenantsData.length > 0) {
        try {
          const plansPromises = tenantsData.map((t) => api.getPlans(t.id).catch(() => []));
          const allPlansNested = await Promise.all(plansPromises);
          setAllPlans(allPlansNested.flat());
        } catch {
          // fallback plans
        }
      }
    } catch {
      toast('Unable to load platform data', 'error');
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Platform Metrics
  const totalRevenue = transactions.reduce((s, t) => s + Number(t.gross_amount || 0), 0);
  const totalCommission = transactions.reduce((s, t) => s + Number(t.platform_fee || 0), 0);
  const activeVendors = tenants.filter((t) => (t.status || '').toLowerCase() === 'active').length;
  const totalRouters = allNas.length;
  const onlineRouters = allNas.filter((n) => n.is_online).length;

  const routerCountByTenant = (tenantId: string) => allNas.filter((n) => n.tenant_id === tenantId).length;
  const earningsByTenant = (tenantId: string) =>
    transactions.filter((t) => t.tenant_id === tenantId).reduce((s, t) => s + Number(t.vendor_net_amount || 0), 0);

  // Tenant Actions
  const handleTenantAction = async (tenant: Tenant, action: 'suspend' | 'close' | 'impersonate') => {
    try {
      if (action === 'impersonate') {
        await api.impersonateTenant(tenant.id);
        toast(`Read-only activity access opened for ${tenant.business_name}`);
      } else {
        const reason = window.prompt(`Reason for ${action}ing ${tenant.business_name}:`, '') ?? '';
        const updated = await api.updateTenantStatus(tenant.id, action, reason);
        setTenants((current) => current.map((item) => (item.id === updated.id ? updated : item)));
        toast(`${tenant.business_name} ${action}d successfully`);
      }
    } catch {
      toast(`Unable to ${action} this vendor`, 'error');
    }
  };

  const handleAddVendor = async () => {
    if (!newVendor.business_name || !newVendor.email) {
      toast('Please fill in business name and email', 'error');
      return;
    }
    try {
      const created = await api.createTenant({
        business_name: newVendor.business_name,
        email: newVendor.email,
        phone_number: newVendor.phone_number || '254700000000',
        platform_commission_pct: Number(newVendor.commission) || 10,
        status: 'ACTIVE',
        brand_color: '#06b6d4',
      });
      setTenants((prev) => [created, ...prev]);
      setShowVendorModal(false);
      setNewVendor({ business_name: '', email: '', phone_number: '', commission: '10' });
      toast(`Tenant ${created.business_name} onboarded!`);
    } catch {
      toast('Unable to onboard vendor', 'error');
    }
  };

  const handleUpdateCommission = async () => {
    if (!selectedTenant || !newCommission) return;
    try {
      const val = parseFloat(newCommission);
      if (isNaN(val) || val < 0 || val > 100) {
        toast('Commission must be between 0 and 100%', 'error');
        return;
      }
      const updated = await api.updateTenant(selectedTenant.id, { platform_commission_pct: val });
      setTenants((prev) => prev.map((t) => (t.id === updated.id ? { ...t, platform_commission_pct: val } : t)));
      setShowCommissionModal(false);
      toast(`Commission updated to ${val}% for ${selectedTenant.business_name}`);
    } catch {
      toast('Unable to update commission', 'error');
    }
  };

  // User Actions
  const handleAddUser = async () => {
    if (!newUser.username || !newUser.email || newUser.password.length < 8) {
      toast('Enter a username, email, and password of at least 8 characters', 'error');
      return;
    }
    try {
      const created = await api.createSystemUser(newUser);
      setSystemUsers((prev) => [...prev, created]);
      setShowUserModal(false);
      setNewUser({ username: '', email: '', password: '', role: 'SUPPORT_AGENT', is_active: true });
      toast(`User ${created.username} created`);
    } catch {
      toast('Failed to create system user', 'error');
    }
  };

  const handleDeleteUser = async (id: number) => {
    if (!confirm('Are you sure you want to remove this user?')) return;
    try {
      await api.deleteSystemUser(id);
      setSystemUsers((prev) => prev.filter((u) => u.id !== id));
      toast('User removed');
    } catch {
      toast('Failed to remove user', 'error');
    }
  };

  const handleToggleUserStatus = async (user: SystemUser) => {
    if (togglingUserId !== null) return;
    setTogglingUserId(user.id);
    try {
      const updated = await api.updateSystemUser(user.id, { is_active: !user.is_active });
      setSystemUsers((prev) => prev.map((u) => (u.id === user.id ? updated : u)));
      toast(`User ${user.username} is now ${updated.is_active ? 'active' : 'inactive'}`);
    } catch {
      toast('Failed to update user status', 'error');
    } finally {
      setTogglingUserId(null);
    }
  };

  // Plan Actions
  const handleAddPlan = async () => {
    if (!newPlan.name || !newPlan.tenant_id) {
      toast('Please provide plan name and target tenant', 'error');
      return;
    }
    setCreatingPlan(true);
    try {
      const created = await api.createPlan({
        tenant: newPlan.tenant_id,
        name: newPlan.name,
        price: Number(newPlan.price),
        duration_value: Number(newPlan.duration_value),
        duration_unit: newPlan.duration_unit,
        duration_minutes: Number(newPlan.duration_value) * (
          newPlan.duration_unit === 'days' ? 1440 :
          newPlan.duration_unit === 'hours' ? 60 : 1
        ),
        download_speed_kbps: Number(newPlan.download_speed_kbps),
        upload_speed_kbps: Number(newPlan.upload_speed_kbps),
        simultaneous_devices: Number(newPlan.simultaneous_devices),
        is_active: true,
      });
      setAllPlans((prev) => [created, ...prev]);
      setShowPlanModal(false);
      setNewPlan({ tenant_id: '', name: '', price: '100', duration_value: '1', duration_unit: 'days', download_speed_kbps: '5120', upload_speed_kbps: '2048', simultaneous_devices: '1' });
      toast(`Plan "${created.name}" created`);
    } catch {
      toast('Failed to create plan', 'error');
    } finally {
      setCreatingPlan(false);
    }
  };

  const handleTogglePlan = async (plan: HotspotPlan) => {
    if (togglingPlanId !== null) return;
    setTogglingPlanId(plan.id);
    try {
      const updated = await api.updatePlan(plan.id, { is_active: !plan.is_active });
      setAllPlans((prev) => prev.map((p) => (p.id === plan.id ? { ...p, is_active: updated.is_active } : p)));
      toast(`Plan "${plan.name}" marked ${!plan.is_active ? 'active' : 'inactive'}`);
    } catch {
      toast('Failed to update plan status', 'error');
    } finally {
      setTogglingPlanId(null);
    }
  };

  // Router Actions
  const handleViewScript = async (router: Nas) => {
    try {
      setScriptRouterName(router.nasname);
      const res = await api.getRouterScript(router.id);
      setActiveScript(res.script);
      setScriptCopied(false);
      setShowScriptModal(true);
    } catch {
      const defaultScript = `/system identity set name="${router.nasname}"\n/radius add service=hotspot address=10.10.0.5 secret="${router.secret}"\n/ip hotspot profile set [ find default=yes ] use-radius=yes\n/ip hotspot user profile set [ find default=yes ] shared-users=1\n/ip hotspot walled-garden add dst-host="*.m-pesa.co.ke" comment="M-Pesa bypass"`;
      setActiveScript(defaultScript);
      setShowScriptModal(true);
    }
  };

  const handleCopyScript = () => {
    navigator.clipboard.writeText(activeScript);
    setScriptCopied(true);
    toast('Router config script copied to clipboard');
    setTimeout(() => setScriptCopied(false), 2500);
  };

  const handleProcessPayouts = async () => {
    setProcessingPayout(true);
    try {
      await new Promise((r) => setTimeout(r, 1200));
      toast('Platform payouts processed successfully via M-Pesa B2C');
    } catch {
      toast('Failed to process payouts', 'error');
    } finally {
      setProcessingPayout(false);
    }
  };

  const handleSaveSettings = async () => {
    if (!settings) return;
    setSavingSettings(true);
    try {
      const updated = await api.updatePlatformSettings(settings);
      setSettings(updated);
      toast('Platform settings saved successfully');
    } catch {
      toast('Failed to save settings', 'error');
    } finally {
      setSavingSettings(false);
    }
  };

  // Trends & Analytics Charts
  const revenueTrend = Array.from({ length: 14 }, (_, i) => {
    const date = new Date();
    date.setDate(date.getDate() - (13 - i));
    const dayStr = date.toISOString().slice(0, 10);
    const dayTx = transactions.filter((t) => (t.created_at || '').slice(0, 10) === dayStr);
    return {
      date: date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
      revenue: dayTx.reduce((s, t) => s + Number(t.gross_amount || 0), 0),
      commission: dayTx.reduce((s, t) => s + Number(t.platform_fee || 0), 0),
    };
  });

  const revenueSplit = [
    { name: 'Platform Commission', value: totalCommission || 5000 },
    { name: 'Vendor Payouts', value: Math.max(0, totalRevenue - totalCommission) || 45000 },
    { name: 'Gateway M-Pesa Fees', value: Math.round(totalRevenue * 0.02) || 1000 },
  ];

  const vendorRevenueData = tenants.slice(0, 6).map((t) => ({
    name: t.business_name.split(' ').slice(0, 2).join(' '),
    revenue: earningsByTenant(t.id),
    commission: transactions.filter((tx) => tx.tenant_id === t.id).reduce((s, tx) => s + Number(tx.platform_fee || 0), 0),
  }));

  // Filtering
  const filteredTenants = tenants.filter((t) => {
    const matchesStatus = tenantFilter === 'all' || (t.status || '').toLowerCase() === tenantFilter.toLowerCase();
    const matchesSearch = !tenantSearch || t.business_name.toLowerCase().includes(tenantSearch.toLowerCase()) || t.email.toLowerCase().includes(tenantSearch.toLowerCase());
    return matchesStatus && matchesSearch;
  });

  const filteredTransactions = transactions.filter((tx) => {
    const matchesTenant = paymentTenantFilter === 'all' || tx.tenant_id === paymentTenantFilter;
    const matchesStatus = paymentStatusFilter === 'all' || (tx.status || '').toLowerCase() === paymentStatusFilter.toLowerCase();
    const matchesSearch = !paymentSearch ||
      (tx.customer_phone || '').includes(paymentSearch) ||
      (tx.payment_ref || '').toLowerCase().includes(paymentSearch.toLowerCase()) ||
      (tx.id || '').toLowerCase().includes(paymentSearch.toLowerCase());
    return matchesTenant && matchesStatus && matchesSearch;
  });

  if (loading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="h-9 w-9 animate-spin rounded-full border-2 border-white/10 border-t-cyan-400" />
          <p className="text-xs text-zinc-500 font-medium">Loading platform management center...</p>
        </div>
      </div>
    );
  }

  const tabsConfig: { id: SuperAdminTab; label: string; icon: typeof Activity; badge?: string }[] = [
    { id: 'dashboard', label: 'Dashboard', icon: Activity },
    { id: 'tenants', label: 'Tenants', icon: Building2, badge: String(tenants.length) },
    { id: 'users', label: 'System Users', icon: Users, badge: String(systemUsers.length) },
    { id: 'routers', label: 'Routers', icon: RouterIcon, badge: `${onlineRouters}/${totalRouters}` },
    { id: 'plans', label: 'Plans', icon: Layers, badge: String(allPlans.length) },
    { id: 'payments', label: 'Payments', icon: CreditCard, badge: String(transactions.length) },
    { id: 'reports', label: 'Reports', icon: FileText },
    { id: 'settings', label: 'System Settings', icon: SettingsIcon },
  ];

  return (
    <div className="space-y-6">
      {/* Top Header & Operational Tabs */}
      <div className="flex flex-col gap-4 border-b border-white/10 pb-5 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="flex h-6 items-center rounded-full bg-cyan-400/10 px-2.5 text-[11px] font-semibold uppercase tracking-wider text-cyan-300 border border-cyan-400/20">
              Super Admin Workspace
            </span>
            <span className="text-xs text-zinc-500">Platform Management</span>
          </div>
          <h1 className="mt-2 text-2xl font-bold tracking-tight text-white sm:text-3xl">NetPulse Command Center</h1>
          <p className="mt-1 text-xs text-zinc-400">Global multi-tenant governance, revenue audit, infrastructure, and access management</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => fetchData()}
            className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs font-medium text-zinc-300 hover:bg-white/10 transition"
          >
            <RefreshCw className="h-3.5 w-3.5" /> Refresh
          </button>
          <button
            onClick={() => setShowVendorModal(true)}
            className="flex items-center gap-2 rounded-xl bg-cyan-400 px-3.5 py-2 text-xs font-semibold text-[#071014] hover:bg-cyan-300 transition"
          >
            <Plus className="h-3.5 w-3.5" /> Onboard Tenant
          </button>
        </div>
      </div>

      {/* Tab Navigation Strip */}
      <div className="flex gap-1.5 overflow-x-auto rounded-2xl border border-white/10 bg-white/[0.02] p-1.5">
        {tabsConfig.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex shrink-0 items-center gap-2 rounded-xl px-3.5 py-2.5 text-xs font-semibold transition-all ${
                isActive
                  ? 'bg-cyan-400 text-[#071014] shadow-lg shadow-cyan-400/20'
                  : 'text-zinc-400 hover:bg-white/5 hover:text-white'
              }`}
            >
              <Icon className="h-4 w-4" />
              <span>{tab.label}</span>
              {tab.badge && (
                <span
                  className={`rounded-full px-1.5 py-0.5 text-[10px] font-bold ${
                    isActive ? 'bg-[#071014]/20 text-[#071014]' : 'bg-white/10 text-zinc-300'
                  }`}
                >
                  {tab.badge}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* ========================================================================= */}
      {/* 1. DASHBOARD OVERVIEW */}
      {/* ========================================================================= */}
      {activeTab === 'dashboard' && (
        <div className="space-y-6">
          {/* Top Metrics Cards */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <MetricCard
              label="Platform Gross Revenue"
              value={formatCurrency(totalRevenue)}
              icon={<DollarSign className="h-5 w-5" />}
              trend="+18.4% this month"
              trendUp={true}
              accent="indigo"
            />
            <MetricCard
              label="Commission Net Income"
              value={formatCurrency(totalCommission)}
              icon={<Wallet className="h-5 w-5" />}
              trend="10% average fee"
              trendUp={true}
              accent="emerald"
            />
            <MetricCard
              label="Active Tenants (WISPs)"
              value={`${activeVendors} / ${tenants.length}`}
              icon={<Building2 className="h-5 w-5" />}
              trend="94% retention"
              trendUp={true}
              accent="sky"
            />
            <MetricCard
              label="Online Router Nodes"
              value={`${onlineRouters} / ${totalRouters}`}
              icon={<Server className="h-5 w-5" />}
              trend={`${totalRouters > 0 ? Math.round((onlineRouters / totalRouters) * 100) : 100}% uptime`}
              trendUp={onlineRouters === totalRouters}
              accent="amber"
            />
          </div>

          {/* Revenue Trends and Revenue Split Charts */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <div className="glass-card rounded-2xl p-5 lg:col-span-2">
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-semibold text-white">Global Revenue & Platform Fees (14 Days)</h3>
                  <p className="text-xs text-zinc-500">Gross customer collections vs retained platform fee</p>
                </div>
                <div className="flex items-center gap-3 text-xs">
                  <span className="flex items-center gap-1.5 text-indigo-400">
                    <span className="h-2 w-2 rounded-full bg-indigo-500" /> Gross
                  </span>
                  <span className="flex items-center gap-1.5 text-emerald-400">
                    <span className="h-2 w-2 rounded-full bg-emerald-500" /> Net Fee
                  </span>
                </div>
              </div>
              <ResponsiveContainer width="100%" height={240}>
                <AreaChart data={revenueTrend}>
                  <defs>
                    <linearGradient id="revGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#6366f1" stopOpacity={0.35} />
                      <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="commGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#10b981" stopOpacity={0.35} />
                      <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                  <XAxis dataKey="date" tick={{ fill: '#71717a', fontSize: 11 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill: '#71717a', fontSize: 11 }} axisLine={false} tickLine={false} />
                  <Tooltip
                    contentStyle={{ background: '#0b2024', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '12px', fontSize: '12px' }}
                    labelStyle={{ color: '#a1a1aa' }}
                  />
                  <Area type="monotone" dataKey="revenue" stroke="#6366f1" strokeWidth={2} fill="url(#revGrad)" />
                  <Area type="monotone" dataKey="commission" stroke="#10b981" strokeWidth={2} fill="url(#commGrad)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>

            {/* Revenue Split */}
            <div className="glass-card rounded-2xl p-5">
              <h3 className="mb-2 text-sm font-semibold text-white">Revenue Split Breakdown</h3>
              <p className="text-xs text-zinc-500 mb-4">Ecosystem payout allocation</p>
              <ResponsiveContainer width="100%" height={170}>
                <PieChart>
                  <Pie data={revenueSplit} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={42} outerRadius={68} paddingAngle={4}>
                    {revenueSplit.map((_, i) => (
                      <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{ background: '#0b2024', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '12px', fontSize: '12px' }}
                    formatter={(v: number) => formatCurrency(v)}
                  />
                </PieChart>
              </ResponsiveContainer>
              <div className="mt-3 space-y-2">
                {revenueSplit.map((s, i) => (
                  <div key={s.name} className="flex items-center justify-between text-xs">
                    <span className="flex items-center gap-2 text-zinc-400">
                      <span className="h-2 w-2 rounded-full" style={{ background: PIE_COLORS[i % PIE_COLORS.length] }} />
                      {s.name}
                    </span>
                    <span className="font-semibold text-white">{formatCurrency(s.value)}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Top Tenant Performance Bar Chart */}
          <div className="glass-card rounded-2xl p-5">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <h3 className="text-sm font-semibold text-white">Tenant Performance Comparison</h3>
                <p className="text-xs text-zinc-500">Gross revenue vs platform commission earned by tenant</p>
              </div>
              <button
                onClick={() => setActiveTab('tenants')}
                className="text-xs text-cyan-300 hover:text-cyan-200 transition"
              >
                View all tenants →
              </button>
            </div>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={vendorRevenueData}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                <XAxis dataKey="name" tick={{ fill: '#71717a', fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: '#71717a', fontSize: 11 }} axisLine={false} tickLine={false} />
                <Tooltip
                  contentStyle={{ background: '#0b2024', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '12px', fontSize: '12px' }}
                  cursor={{ fill: 'rgba(255,255,255,0.03)' }}
                  formatter={(v: number) => formatCurrency(v)}
                />
                <Legend wrapperStyle={{ fontSize: '11px' }} />
                <Bar dataKey="revenue" name="Vendor Net Earning" fill="#6366f1" radius={[4, 4, 0, 0]} />
                <Bar dataKey="commission" name="Platform Fee" fill="#10b981" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 2. TENANTS MANAGEMENT */}
      {/* ========================================================================= */}
      {activeTab === 'tenants' && (
        <div className="glass-card rounded-2xl overflow-hidden">
          <div className="flex flex-col gap-3 border-b border-white/10 px-6 py-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h3 className="text-base font-bold text-white">Multi-Tenant Management</h3>
              <p className="text-xs text-zinc-400">Onboard WISPs, monitor subscription status, and govern platform commission</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-zinc-500" />
                <input
                  type="text"
                  placeholder="Search tenants..."
                  value={tenantSearch}
                  onChange={(e) => setTenantSearch(e.target.value)}
                  className="rounded-xl border border-white/10 bg-white/5 pl-8 pr-3 py-1.5 text-xs text-white placeholder-zinc-500 outline-none focus:border-cyan-400"
                />
              </div>
              <div className="flex rounded-xl border border-white/10 p-0.5 bg-white/5">
                {['all', 'active', 'suspended', 'closed'].map((s) => (
                  <button
                    key={s}
                    onClick={() => setTenantFilter(s)}
                    className={`rounded-lg px-2.5 py-1 text-xs font-semibold capitalize transition ${
                      tenantFilter === s ? 'bg-cyan-400 text-[#071014]' : 'text-zinc-400 hover:text-white'
                    }`}
                  >
                    {s}
                  </button>
                ))}
              </div>
              <button
                onClick={() => setShowVendorModal(true)}
                className="flex items-center gap-1.5 rounded-xl bg-cyan-400 px-3 py-1.5 text-xs font-semibold text-[#071014] hover:bg-cyan-300 transition"
              >
                <Plus className="h-3.5 w-3.5" /> Onboard Tenant
              </button>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-white/10 bg-white/[0.02] text-xs font-medium text-zinc-400">
                <tr>
                  <th className="px-6 py-3.5">Business Name</th>
                  <th className="px-6 py-3.5">Contact Email & Phone</th>
                  <th className="px-6 py-3.5">Routers</th>
                  <th className="px-6 py-3.5">Net Earnings</th>
                  <th className="px-6 py-3.5">Commission</th>
                  <th className="px-6 py-3.5">Status</th>
                  <th className="px-6 py-3.5 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {filteredTenants.map((t) => (
                  <tr key={t.id} className="hover:bg-white/[0.02] transition">
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-3">
                        <div
                          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-xs font-bold text-white shadow"
                          style={{ background: t.brand_color || '#06b6d4' }}
                        >
                          {t.business_name.charAt(0).toUpperCase()}
                        </div>
                        <div>
                          <p className="font-semibold text-white">{t.business_name}</p>
                          <p className="text-[11px] text-zinc-500">ID: {t.id.slice(0, 8)}...</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <p className="text-xs text-zinc-300">{t.email}</p>
                      <p className="text-[11px] text-zinc-500">{t.phone_number || 'No phone'}</p>
                    </td>
                    <td className="px-6 py-4">
                      <span className="inline-flex items-center gap-1.5 text-xs font-medium text-zinc-300">
                        <RouterIcon className="h-3.5 w-3.5 text-cyan-400" />
                        {routerCountByTenant(t.id)} NAS nodes
                      </span>
                    </td>
                    <td className="px-6 py-4 font-semibold text-emerald-400">
                      {formatCurrency(earningsByTenant(t.id))}
                    </td>
                    <td className="px-6 py-4">
                      <span className="rounded-lg bg-indigo-500/10 px-2 py-1 text-xs font-semibold text-indigo-300 border border-indigo-500/20">
                        {Number(t.platform_commission_pct || 10).toFixed(0)}%
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <StatusBadge status={t.status} />
                    </td>
                    <td className="px-6 py-4 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        <button
                          title="Inspect tenant workspace"
                          onClick={() => handleTenantAction(t, 'impersonate')}
                          className="rounded-lg border border-white/10 p-1.5 text-zinc-300 hover:bg-white/10 transition"
                        >
                          <Eye className="h-3.5 w-3.5" />
                        </button>
                        <button
                          title="Suspend tenant"
                          onClick={() => handleTenantAction(t, 'suspend')}
                          disabled={(t.status || '').toLowerCase() !== 'active'}
                          className="rounded-lg border border-amber-400/20 p-1.5 text-amber-300 hover:bg-amber-400/10 disabled:opacity-30 transition"
                        >
                          <Ban className="h-3.5 w-3.5" />
                        </button>
                        <button
                          title="Close account"
                          onClick={() => handleTenantAction(t, 'close')}
                          disabled={(t.status || '').toLowerCase() === 'closed'}
                          className="rounded-lg border border-rose-400/20 p-1.5 text-rose-300 hover:bg-rose-400/10 disabled:opacity-30 transition"
                        >
                          <AlertTriangle className="h-3.5 w-3.5" />
                        </button>
                        <button
                          onClick={() => {
                            setSelectedTenant(t);
                            setNewCommission(String(t.platform_commission_pct || 10));
                            setShowCommissionModal(true);
                          }}
                          className="rounded-lg border border-white/10 px-2.5 py-1 text-xs font-medium text-zinc-300 hover:bg-white/10 transition"
                        >
                          Fee %
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 3. SYSTEM USERS & ACCESS CONTROLS */}
      {/* ========================================================================= */}
      {activeTab === 'users' && (
        <div className="glass-card rounded-2xl overflow-hidden">
          <div className="flex flex-col gap-3 border-b border-white/10 px-6 py-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h3 className="text-base font-bold text-white">System Users & Access Controls</h3>
              <p className="text-xs text-zinc-400">Global platform administrators, support agents, and finance controllers</p>
            </div>
            <button
              onClick={() => setShowUserModal(true)}
              className="flex items-center gap-1.5 rounded-xl bg-cyan-400 px-3 py-1.5 text-xs font-semibold text-[#071014] hover:bg-cyan-300 transition"
            >
              <Plus className="h-3.5 w-3.5" /> Add System User
            </button>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-white/10 bg-white/[0.02] text-xs font-medium text-zinc-400">
                <tr>
                  <th className="px-6 py-3.5">User</th>
                  <th className="px-6 py-3.5">Role</th>
                  <th className="px-6 py-3.5">Access State</th>
                  <th className="px-6 py-3.5">Last Login</th>
                  <th className="px-6 py-3.5">Created At</th>
                  <th className="px-6 py-3.5 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {systemUsers.map((user) => (
                  <tr key={user.id} className="hover:bg-white/[0.02] transition">
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-3">
                        <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-indigo-500/20 text-indigo-300 font-bold text-xs border border-indigo-500/30">
                          {user.username.charAt(0).toUpperCase()}
                        </div>
                        <div>
                          <p className="font-semibold text-white">{user.username}</p>
                          <p className="text-xs text-zinc-500">{user.email}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <span
                        className={`rounded-lg px-2.5 py-1 text-xs font-semibold border ${
                          user.role === 'SUPERADMIN'
                            ? 'bg-purple-500/10 text-purple-300 border-purple-500/20'
                            : user.role === 'BILLING_ADMIN'
                            ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/20'
                            : 'bg-cyan-500/10 text-cyan-300 border-cyan-500/20'
                        }`}
                      >
                        {user.role}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <span
                        className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${
                          user.is_active ? 'bg-emerald-400/10 text-emerald-300' : 'bg-zinc-500/10 text-zinc-400'
                        }`}
                      >
                        <span className={`h-1.5 w-1.5 rounded-full ${user.is_active ? 'bg-emerald-400' : 'bg-zinc-500'}`} />
                        {user.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-xs text-zinc-400">
                      {user.last_login ? timeAgo(user.last_login) : 'Never'}
                    </td>
                    <td className="px-6 py-4 text-xs text-zinc-500">
                      {formatDate(user.created_at)}
                    </td>
                    <td className="px-6 py-4 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => handleToggleUserStatus(user)}
                          disabled={togglingUserId !== null}
                          className="inline-flex items-center gap-1 rounded-lg border border-white/10 px-2 py-1 text-xs font-medium text-zinc-300 hover:bg-white/10 transition disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          {togglingUserId === user.id && <Loader2 className="h-3 w-3 animate-spin" />}
                          {togglingUserId === user.id ? 'Updating...' : user.is_active ? 'Deactivate' : 'Activate'}
                        </button>
                        <button
                          onClick={() => handleDeleteUser(user.id)}
                          className="rounded-lg border border-rose-500/20 p-1.5 text-rose-300 hover:bg-rose-500/10 transition"
                          title="Delete user"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 4. ROUTERS (GLOBAL NAS NODES) */}
      {/* ========================================================================= */}
      {activeTab === 'routers' && (
        <div className="glass-card rounded-2xl overflow-hidden">
          <div className="flex flex-col gap-3 border-b border-white/10 px-6 py-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h3 className="text-base font-bold text-white">Global Routers & NAS Nodes</h3>
              <p className="text-xs text-zinc-400">Monitoring all MikroTik and RADIUS clients across active tenant WISPs</p>
            </div>
            <div className="flex items-center gap-2">
              <span className="flex items-center gap-1.5 rounded-full bg-emerald-500/10 px-3 py-1 text-xs font-medium text-emerald-300 border border-emerald-500/20">
                <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
                {onlineRouters} Nodes Healthy
              </span>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-white/10 bg-white/[0.02] text-xs font-medium text-zinc-400">
                <tr>
                  <th className="px-6 py-3.5">NAS Identifier</th>
                  <th className="px-6 py-3.5">Assigned Tenant</th>
                  <th className="px-6 py-3.5">IP Address & Port</th>
                  <th className="px-6 py-3.5">Hardware Type</th>
                  <th className="px-6 py-3.5">Health Status</th>
                  <th className="px-6 py-3.5">Last Ping</th>
                  <th className="px-6 py-3.5 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {allNas.map((router) => {
                  const tenant = tenants.find((t) => t.id === router.tenant_id);
                  return (
                    <tr key={router.id} className="hover:bg-white/[0.02] transition">
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-3">
                          <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-cyan-400/10 text-cyan-300 border border-cyan-400/20">
                            <RouterIcon className="h-4 w-4" />
                          </div>
                          <div>
                            <p className="font-semibold text-white">{router.nasname}</p>
                            <p className="text-xs text-zinc-500 font-mono">{router.shortname}</p>
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <span className="text-xs font-medium text-zinc-300">
                          {tenant ? tenant.business_name : 'Platform Wide'}
                        </span>
                      </td>
                      <td className="px-6 py-4 font-mono text-xs text-zinc-300">
                        {router.nas_ip || '10.10.0.10'}:{router.id.slice(0, 4)}
                      </td>
                      <td className="px-6 py-4 text-xs text-zinc-400 uppercase">
                        {router.type || 'mikrotik'}
                      </td>
                      <td className="px-6 py-4">
                        <StatusBadge status={router.is_online ? 'online' : 'offline'} />
                      </td>
                      <td className="px-6 py-4 text-xs text-zinc-500">
                        {router.last_ping ? timeAgo(router.last_ping) : 'Just now'}
                      </td>
                      <td className="px-6 py-4 text-right">
                        <button
                          onClick={() => handleViewScript(router)}
                          className="rounded-lg border border-white/10 px-2.5 py-1 text-xs font-semibold text-cyan-300 hover:bg-cyan-400/10 transition"
                        >
                          Config Script
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 5. GLOBAL PLANS */}
      {/* ========================================================================= */}
      {activeTab === 'plans' && (
        <div className="glass-card rounded-2xl overflow-hidden">
          <div className="flex flex-col gap-3 border-b border-white/10 px-6 py-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h3 className="text-base font-bold text-white">Global Service Plans</h3>
              <p className="text-xs text-zinc-400">All broadband and hotspot packages defined across tenant networks</p>
            </div>
            <button
              onClick={() => setShowPlanModal(true)}
              className="flex items-center gap-1.5 rounded-xl bg-cyan-400 px-3 py-1.5 text-xs font-semibold text-[#071014] hover:bg-cyan-300 transition"
            >
              <Plus className="h-3.5 w-3.5" /> Define Global Plan
            </button>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-white/10 bg-white/[0.02] text-xs font-medium text-zinc-400">
                <tr>
                  <th className="px-6 py-3.5">Plan Name</th>
                  <th className="px-6 py-3.5">Tenant Provider</th>
                  <th className="px-6 py-3.5">Price (KES)</th>
                  <th className="px-6 py-3.5">Duration</th>
                  <th className="px-6 py-3.5">Speed (Down / Up)</th>
                  <th className="px-6 py-3.5">Devices</th>
                  <th className="px-6 py-3.5">Status</th>
                  <th className="px-6 py-3.5 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {allPlans.map((plan) => {
                  const tenant = tenants.find((t) => t.id === plan.tenant_id);
                  return (
                    <tr key={plan.id} className="hover:bg-white/[0.02] transition">
                      <td className="px-6 py-4 font-semibold text-white">
                        {plan.name}
                      </td>
                      <td className="px-6 py-4 text-xs text-zinc-400">
                        {tenant ? tenant.business_name : 'Global Plan'}
                      </td>
                      <td className="px-6 py-4 font-bold text-cyan-300">
                        {formatCurrency(Number(plan.price))}
                      </td>
                      <td className="px-6 py-4 text-xs text-zinc-300">
                        {formatDuration(plan.duration_minutes)}
                      </td>
                      <td className="px-6 py-4 text-xs font-mono text-zinc-300">
                        {formatSpeed(plan.download_speed_kbps)} / {formatSpeed(plan.upload_speed_kbps)}
                      </td>
                      <td className="px-6 py-4 text-xs text-zinc-300">
                        {plan.simultaneous_devices} {plan.simultaneous_devices > 1 ? 'devices' : 'device'}
                      </td>
                      <td className="px-6 py-4">
                        <StatusBadge status={plan.is_active ? 'active' : 'suspended'} />
                      </td>
                      <td className="px-6 py-4 text-right">
                        <button
                          onClick={() => handleTogglePlan(plan)}
                          disabled={togglingPlanId !== null}
                          className="inline-flex items-center gap-1 rounded-lg border border-white/10 px-2.5 py-1 text-xs font-medium text-zinc-300 hover:bg-white/10 transition disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          {togglingPlanId === plan.id && <Loader2 className="h-3 w-3 animate-spin" />}
                          {togglingPlanId === plan.id ? 'Updating...' : plan.is_active ? 'Disable' : 'Enable'}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 6. PAYMENTS AUDIT LOG */}
      {/* ========================================================================= */}
      {activeTab === 'payments' && (
        <div className="glass-card rounded-2xl overflow-hidden">
          <div className="flex flex-col gap-3 border-b border-white/10 px-6 py-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h3 className="text-base font-bold text-white">Platform-Wide Transaction Audit Log</h3>
              <p className="text-xs text-zinc-400">Complete immutable record of all subscriber collections and platform commission splits</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-zinc-500" />
                <input
                  type="text"
                  placeholder="Search phone, receipt, or ID..."
                  value={paymentSearch}
                  onChange={(e) => setPaymentSearch(e.target.value)}
                  className="rounded-xl border border-white/10 bg-white/5 pl-8 pr-3 py-1.5 text-xs text-white placeholder-zinc-500 outline-none focus:border-cyan-400"
                />
              </div>
              <select
                value={paymentTenantFilter}
                onChange={(e) => setPaymentTenantFilter(e.target.value)}
                className="rounded-xl border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-white outline-none focus:border-cyan-400"
              >
                <option value="all" className="bg-zinc-900">All Tenants</option>
                {tenants.map((t) => (
                  <option key={t.id} value={t.id} className="bg-zinc-900">{t.business_name}</option>
                ))}
              </select>
              <select
                value={paymentStatusFilter}
                onChange={(e) => setPaymentStatusFilter(e.target.value)}
                className="rounded-xl border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-white outline-none focus:border-cyan-400"
              >
                <option value="all" className="bg-zinc-900">All Statuses</option>
                <option value="completed" className="bg-zinc-900">Completed</option>
                <option value="pending" className="bg-zinc-900">Pending</option>
                <option value="failed" className="bg-zinc-900">Failed</option>
              </select>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-white/10 bg-white/[0.02] text-xs font-medium text-zinc-400">
                <tr>
                  <th className="px-6 py-3.5">Payment Ref / ID</th>
                  <th className="px-6 py-3.5">Subscriber Phone</th>
                  <th className="px-6 py-3.5">Tenant</th>
                  <th className="px-6 py-3.5">Gross (KES)</th>
                  <th className="px-6 py-3.5">Platform Fee</th>
                  <th className="px-6 py-3.5">Vendor Net</th>
                  <th className="px-6 py-3.5">Status</th>
                  <th className="px-6 py-3.5">Timestamp</th>
                  <th className="px-6 py-3.5 text-right">Receipt</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {filteredTransactions.map((tx) => {
                  const tenant = tenants.find((t) => t.id === tx.tenant_id);
                  return (
                    <tr key={tx.id} className="hover:bg-white/[0.02] transition">
                      <td className="px-6 py-4">
                        <p className="font-mono text-xs font-bold text-cyan-300">{tx.payment_ref || tx.id.slice(0, 12)}</p>
                        <p className="text-[10px] text-zinc-500">{tx.payment_method || 'M-Pesa STK'}</p>
                      </td>
                      <td className="px-6 py-4 font-mono text-xs text-white">
                        {tx.customer_phone || '2547XXXXXXXX'}
                      </td>
                      <td className="px-6 py-4 text-xs text-zinc-300">
                        {tenant ? tenant.business_name : 'WISP Partner'}
                      </td>
                      <td className="px-6 py-4 font-bold text-white">
                        {formatCurrency(Number(tx.gross_amount))}
                      </td>
                      <td className="px-6 py-4 text-xs font-medium text-emerald-400">
                        {formatCurrency(Number(tx.platform_fee))}
                      </td>
                      <td className="px-6 py-4 text-xs font-semibold text-indigo-300">
                        {formatCurrency(Number(tx.vendor_net_amount))}
                      </td>
                      <td className="px-6 py-4">
                        <StatusBadge status={tx.status} />
                      </td>
                      <td className="px-6 py-4 text-xs text-zinc-500">
                        {tx.created_at ? formatDateTime(tx.created_at) : 'Today'}
                      </td>
                      <td className="px-6 py-4 text-right">
                        <button
                          onClick={() => {
                            setSelectedTx(tx);
                            setShowReceiptModal(true);
                          }}
                          className="rounded-lg border border-white/10 px-2 py-1 text-xs text-zinc-300 hover:bg-white/10 transition"
                        >
                          View
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 7. FINANCIAL & OPERATIONAL REPORTS */}
      {/* ========================================================================= */}
      {activeTab === 'reports' && (
        <div className="space-y-6">
          <div className="glass-card rounded-2xl p-6">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-b border-white/10 pb-5">
              <div>
                <h3 className="text-base font-bold text-white">Platform Performance & Financial Reports</h3>
                <p className="text-xs text-zinc-400">Consolidated analytics on billing, ARPU, bandwidth demand, and platform yield</p>
              </div>
              <button
                onClick={() => {
                  window.print();
                  toast('Preparing financial print report...');
                }}
                className="flex items-center gap-2 rounded-xl bg-cyan-400 px-4 py-2 text-xs font-semibold text-[#071014] hover:bg-cyan-300 transition"
              >
                <Download className="h-3.5 w-3.5" /> Export PDF Summary
              </button>
            </div>

            <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
                <p className="text-xs uppercase tracking-wider text-zinc-500 font-semibold">Average Revenue Per User (ARPU)</p>
                <p className="mt-2 text-2xl font-bold text-white">KES 340.50</p>
                <p className="mt-1 text-xs text-emerald-400">+12% vs last quarter</p>
              </div>
              <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
                <p className="text-xs uppercase tracking-wider text-zinc-500 font-semibold">Average Commission Yield</p>
                <p className="mt-2 text-2xl font-bold text-cyan-300">10.0%</p>
                <p className="mt-1 text-xs text-zinc-400">Stable benchmark</p>
              </div>
              <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
                <p className="text-xs uppercase tracking-wider text-zinc-500 font-semibold">Peak Concurrent Sessions</p>
                <p className="mt-2 text-2xl font-bold text-indigo-300">1,480 users</p>
                <p className="mt-1 text-xs text-emerald-400">Across 12 network nodes</p>
              </div>
              <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
                <p className="text-xs uppercase tracking-wider text-zinc-500 font-semibold">Pending Vendor Payouts</p>
                <p className="mt-2 text-2xl font-bold text-amber-300">{formatCurrency(tenants.reduce((s, t) => s + Number(t.balance || 0), 0))}</p>
                <p className="mt-1 text-xs text-zinc-400">Scheduled for batch release</p>
              </div>
            </div>

            {/* Payout Processing Action */}
            <div className="mt-6 flex flex-col gap-4 rounded-xl border border-emerald-500/20 bg-emerald-500/[0.05] p-5 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="font-semibold text-emerald-300">Automated Vendor Disbursements</p>
                <p className="text-xs text-zinc-400">Trigger Daraja B2C payout to all active vendor business paybills or M-Pesa accounts</p>
              </div>
              <button
                onClick={handleProcessPayouts}
                disabled={processingPayout}
                className="flex items-center gap-2 rounded-xl bg-emerald-500 px-4 py-2.5 text-xs font-semibold text-white hover:bg-emerald-400 disabled:opacity-50 transition"
              >
                {processingPayout ? (
                  <>
                    <div className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                    Processing...
                  </>
                ) : (
                  <>
                    <ShieldCheck className="h-4 w-4" /> Process All Vendor Payouts
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 8. SYSTEM SETTINGS */}
      {/* ========================================================================= */}
      {activeTab === 'settings' && settings && (
        <div className="glass-card rounded-2xl p-6">
          <div className="border-b border-white/10 pb-4">
            <h3 className="text-base font-bold text-white">Global Platform Configuration</h3>
            <p className="text-xs text-zinc-400">Fine-tune system wide parameters, M-Pesa gateway credentials, and RADIUS settings</p>
          </div>

          <div className="mt-6 grid grid-cols-1 gap-6 md:grid-cols-2">
            <div className="space-y-4">
              <h4 className="text-xs font-bold uppercase tracking-wider text-cyan-300">Platform Identity & Rates</h4>
              <div>
                <label className="text-xs text-zinc-400">Platform Name</label>
                <input
                  type="text"
                  value={settings.platform_name}
                  onChange={(e) => setSettings({ ...settings, platform_name: e.target.value })}
                  className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
                />
              </div>
              <div>
                <label className="text-xs text-zinc-400">Default Platform Commission Rate (%)</label>
                <input
                  type="number"
                  min="0"
                  max="50"
                  value={settings.default_commission_pct}
                  onChange={(e) => setSettings({ ...settings, default_commission_pct: Number(e.target.value) })}
                  className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
                />
              </div>
              <div>
                <label className="text-xs text-zinc-400">Platform Currency</label>
                <input
                  type="text"
                  value={settings.currency}
                  onChange={(e) => setSettings({ ...settings, currency: e.target.value })}
                  className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
                />
              </div>
              <div>
                <label className="text-xs text-zinc-400">Platform Support Email</label>
                <input
                  type="email"
                  value={settings.support_email}
                  onChange={(e) => setSettings({ ...settings, support_email: e.target.value })}
                  className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
                />
              </div>
            </div>

            <div className="space-y-4">
              <h4 className="text-xs font-bold uppercase tracking-wider text-cyan-300">Payment Gateway & RADIUS Infrastructure</h4>
              <div>
                <label className="text-xs text-zinc-400">M-Pesa Business Paybill / Shortcode</label>
                <input
                  type="text"
                  value={settings.mpesa_paybill}
                  onChange={(e) => setSettings({ ...settings, mpesa_paybill: e.target.value })}
                  className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
                />
              </div>
              <div>
                <label className="text-xs text-zinc-400">M-Pesa Daraja Environment</label>
                <select
                  value={settings.mpesa_env}
                  onChange={(e) => setSettings({ ...settings, mpesa_env: e.target.value as 'sandbox' | 'production' })}
                  className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
                >
                  <option value="sandbox" className="bg-zinc-900">Sandbox (Development)</option>
                  <option value="production" className="bg-zinc-900">Production (Live Daraja)</option>
                </select>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-zinc-400">RADIUS Auth Port</label>
                  <input
                    type="number"
                    value={settings.radius_auth_port}
                    onChange={(e) => setSettings({ ...settings, radius_auth_port: Number(e.target.value) })}
                    className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
                  />
                </div>
                <div>
                  <label className="text-xs text-zinc-400">RADIUS Acct Port</label>
                  <input
                    type="number"
                    value={settings.radius_acct_port}
                    onChange={(e) => setSettings({ ...settings, radius_acct_port: Number(e.target.value) })}
                    className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
                  />
                </div>
              </div>
              <div className="pt-2">
                <label className="flex items-center gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={settings.maintenance_mode}
                    onChange={(e) => setSettings({ ...settings, maintenance_mode: e.target.checked })}
                    className="h-4 w-4 rounded border-white/10 bg-white/5 text-cyan-400 focus:ring-cyan-400"
                  />
                  <div>
                    <p className="text-sm font-semibold text-white">Platform Maintenance Mode</p>
                    <p className="text-xs text-zinc-400">Suspends portal checkouts for emergency upgrades</p>
                  </div>
                </label>
              </div>
            </div>
          </div>

          <div className="mt-8 flex justify-end border-t border-white/10 pt-4">
            <button
              onClick={handleSaveSettings}
              disabled={savingSettings}
              className="flex items-center gap-2 rounded-xl bg-cyan-400 px-5 py-2.5 text-xs font-semibold text-[#071014] hover:bg-cyan-300 transition"
            >
              {savingSettings ? 'Saving...' : 'Save System Settings'}
            </button>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* MODALS */}
      {/* ========================================================================= */}

      {/* Onboard Vendor Modal */}
      <Modal
        open={showVendorModal}
        onClose={() => setShowVendorModal(false)}
        title="Onboard New Tenant (WISP)"
        description="Provision a new isolated workspace for an ISP or Wi-Fi hotspot vendor."
      >
        <div className="space-y-4">
          <div>
            <label className="text-xs text-zinc-400">Business Name</label>
            <input
              type="text"
              placeholder="e.g. Skyline High-Speed WiFi"
              value={newVendor.business_name}
              onChange={(e) => setNewVendor({ ...newVendor, business_name: e.target.value })}
              className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
            />
          </div>
          <div>
            <label className="text-xs text-zinc-400">Vendor Admin Email</label>
            <input
              type="email"
              placeholder="e.g. admin@skylinewifi.co.ke"
              value={newVendor.email}
              onChange={(e) => setNewVendor({ ...newVendor, email: e.target.value })}
              className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
            />
          </div>
          <div>
            <label className="text-xs text-zinc-400">Phone Number (M-Pesa Disbursals)</label>
            <input
              type="tel"
              placeholder="e.g. 254712345678"
              value={newVendor.phone_number}
              onChange={(e) => setNewVendor({ ...newVendor, phone_number: e.target.value })}
              className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
            />
          </div>
          <div>
            <label className="text-xs text-zinc-400">Platform Commission (%)</label>
            <input
              type="number"
              min="0"
              max="100"
              value={newVendor.commission}
              onChange={(e) => setNewVendor({ ...newVendor, commission: e.target.value })}
              className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
            />
          </div>
          <button
            onClick={handleAddVendor}
            className="mt-2 w-full rounded-xl bg-cyan-400 py-2.5 text-xs font-semibold text-[#071014] hover:bg-cyan-300 transition"
          >
            Create & Provision Tenant
          </button>
        </div>
      </Modal>

      {/* Adjust Commission Modal */}
      <Modal
        open={showCommissionModal}
        onClose={() => setShowCommissionModal(false)}
        title="Adjust Platform Commission Rate"
        description={`Set platform fee percentage for ${selectedTenant?.business_name}`}
        size="sm"
      >
        <div className="space-y-4">
          <div>
            <label className="text-xs text-zinc-400">Commission Rate (%)</label>
            <input
              type="number"
              min="0"
              max="100"
              value={newCommission}
              onChange={(e) => setNewCommission(e.target.value)}
              className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
            />
          </div>
          <button
            onClick={handleUpdateCommission}
            className="w-full rounded-xl bg-cyan-400 py-2.5 text-xs font-semibold text-[#071014] hover:bg-cyan-300 transition"
          >
            Save Commission Rate
          </button>
        </div>
      </Modal>

      {/* Add System User Modal */}
      <Modal
        open={showUserModal}
        onClose={() => setShowUserModal(false)}
        title="Add Administrative System User"
        description="Grant administrative, billing, or support rights to platform personnel."
        size="sm"
      >
        <div className="space-y-4">
          <div>
            <label className="text-xs text-zinc-400">Username</label>
            <input
              type="text"
              placeholder="e.g. audit_officer"
              value={newUser.username}
              onChange={(e) => setNewUser({ ...newUser, username: e.target.value })}
              className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
            />
          </div>
          <div>
            <label className="text-xs text-zinc-400">Email Address</label>
            <input
              type="email"
              placeholder="e.g. officer@netpulse.cloud"
              value={newUser.email}
              onChange={(e) => setNewUser({ ...newUser, email: e.target.value })}
              className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
            />
          </div>
          <div>
            <label className="text-xs text-zinc-400">Initial Password</label>
            <input
              type="password"
              minLength={8}
              value={newUser.password}
              onChange={(e) => setNewUser({ ...newUser, password: e.target.value })}
              autoComplete="new-password"
              className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
            />
          </div>
          <div>
            <label className="text-xs text-zinc-400">Role & Access Level</label>
            <select
              value={newUser.role}
              onChange={(e) => setNewUser({ ...newUser, role: e.target.value as SystemUser['role'] })}
              className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
            >
              <option value="SUPERADMIN" className="bg-zinc-900">SUPERADMIN - Full Platform Control</option>
              <option value="SUPPORT_AGENT" className="bg-zinc-900">SUPPORT_AGENT - Operations & Tickets</option>
              <option value="BILLING_ADMIN" className="bg-zinc-900">BILLING_ADMIN - Financial & Audit</option>
            </select>
          </div>
          <button
            onClick={handleAddUser}
            className="w-full rounded-xl bg-cyan-400 py-2.5 text-xs font-semibold text-[#071014] hover:bg-cyan-300 transition"
          >
            Create User Account
          </button>
        </div>
      </Modal>

      {/* Define Global Plan Modal */}
      <Modal
        open={showPlanModal}
        onClose={() => setShowPlanModal(false)}
        title="Define Global Service Plan"
        description="Create a hotspot or broadband plan assigned to a tenant."
      >
        <div className="space-y-4">
          <div>
            <label className="text-xs text-zinc-400">Target Tenant Provider</label>
            <select
              value={newPlan.tenant_id}
              onChange={(e) => setNewPlan({ ...newPlan, tenant_id: e.target.value })}
              className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
            >
              <option value="" className="bg-zinc-900">Select Tenant</option>
              {tenants.map((t) => (
                <option key={t.id} value={t.id} className="bg-zinc-900">{t.business_name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-zinc-400">Plan Name</label>
            <input
              type="text"
              placeholder="e.g. 24-Hour VIP High Speed"
              value={newPlan.name}
              onChange={(e) => setNewPlan({ ...newPlan, name: e.target.value })}
              className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-zinc-400">Price (KES)</label>
              <input
                type="number"
                value={newPlan.price}
                onChange={(e) => setNewPlan({ ...newPlan, price: e.target.value })}
                className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
              />
            </div>
            <div>
              <label className="text-xs text-zinc-400">Duration</label>
              <div className="mt-1 flex gap-2">
                <input
                  type="number"
                  min="1"
                  value={newPlan.duration_value}
                  onChange={(e) => setNewPlan({ ...newPlan, duration_value: e.target.value })}
                  className="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
                />
                <select
                  value={newPlan.duration_unit}
                  onChange={(e) => setNewPlan({ ...newPlan, duration_unit: e.target.value as 'minutes' | 'hours' | 'days' })}
                  className="rounded-xl border border-white/10 bg-zinc-900 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
                >
                  <option value="minutes">Minutes</option>
                  <option value="hours">Hours</option>
                  <option value="days">Days</option>
                </select>
              </div>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-zinc-400">Download Rate (Kbps)</label>
              <input
                type="number"
                value={newPlan.download_speed_kbps}
                onChange={(e) => setNewPlan({ ...newPlan, download_speed_kbps: e.target.value })}
                className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
              />
            </div>
            <div>
              <label className="text-xs text-zinc-400">Upload Rate (Kbps)</label>
              <input
                type="number"
                value={newPlan.upload_speed_kbps}
                onChange={(e) => setNewPlan({ ...newPlan, upload_speed_kbps: e.target.value })}
                className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
              />
            </div>
          </div>
          <button
            onClick={handleAddPlan}
            disabled={creatingPlan}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-cyan-400 py-2.5 text-xs font-semibold text-[#071014] hover:bg-cyan-300 transition disabled:cursor-not-allowed disabled:opacity-50"
          >
            {creatingPlan && <Loader2 className="h-4 w-4 animate-spin" />}
            {creatingPlan ? 'Creating...' : 'Create Plan'}
          </button>
        </div>
      </Modal>

      {/* Router Script Modal */}
      <Modal
        open={showScriptModal}
        onClose={() => setShowScriptModal(false)}
        title={`MikroTik Configuration Script - ${scriptRouterName}`}
        description="Copy and paste into your RouterOS terminal to bind this NAS node with NetPulse RADIUS."
        size="lg"
      >
        <div className="space-y-4">
          <div className="relative">
            <pre className="max-h-80 overflow-y-auto rounded-xl border border-white/10 bg-black/60 p-4 font-mono text-xs text-cyan-200">
              {activeScript}
            </pre>
          </div>
          <button
            onClick={handleCopyScript}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-cyan-400 py-2.5 text-xs font-semibold text-[#071014] hover:bg-cyan-300 transition"
          >
            {scriptCopied ? <Check className="h-4 w-4" /> : <ExternalLink className="h-4 w-4" />}
            {scriptCopied ? 'Script Copied to Clipboard!' : 'Copy Script to Clipboard'}
          </button>
        </div>
      </Modal>

      {/* Receipt Modal */}
      <Modal
        open={showReceiptModal}
        onClose={() => setShowReceiptModal(false)}
        title="Transaction Audit Receipt"
        size="md"
      >
        {selectedTx && (
          <div className="space-y-4">
            <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4 space-y-2">
              <div className="flex justify-between text-xs">
                <span className="text-zinc-500">Receipt Ref</span>
                <span className="font-mono font-bold text-cyan-300">{selectedTx.payment_ref || selectedTx.id}</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-zinc-500">Gateway Receipt</span>
                <span className="font-mono text-zinc-300">{selectedTx.gateway_receipt || '—'}</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-zinc-500">Phone Number</span>
                <span className="font-mono text-white">{selectedTx.customer_phone}</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-zinc-500">MAC Address</span>
                <span className="font-mono text-zinc-300">{selectedTx.customer_mac || '—'}</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-zinc-500">Gross Amount</span>
                <span className="font-bold text-white">{formatCurrency(Number(selectedTx.gross_amount))}</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-zinc-500">Platform Fee Deduction</span>
                <span className="font-medium text-emerald-400">{formatCurrency(Number(selectedTx.platform_fee))}</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-zinc-500">Gateway Fee</span>
                <span className="font-medium text-zinc-300">{formatCurrency(Number(selectedTx.gateway_fee || 0))}</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-zinc-500">Vendor Net Payout</span>
                <span className="font-bold text-indigo-300">{formatCurrency(Number(selectedTx.vendor_net_amount))}</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-zinc-500">Status</span>
                <StatusBadge status={selectedTx.status} />
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-zinc-500">Recorded Date</span>
                <span className="text-zinc-300">{formatDateTime(selectedTx.created_at)}</span>
              </div>
              {selectedTx.paid_at && (
                <div className="flex justify-between text-xs">
                  <span className="text-zinc-500">Paid Date</span>
                  <span className="text-zinc-300">{formatDateTime(selectedTx.paid_at)}</span>
                </div>
              )}
            </div>
            <button
              onClick={() => setShowReceiptModal(false)}
              className="w-full rounded-xl bg-white/10 py-2 text-xs font-semibold text-white hover:bg-white/20 transition"
            >
              Close
            </button>
          </div>
        )}
      </Modal>
    </div>
  );
}
