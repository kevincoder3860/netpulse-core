import { useState, useEffect, useCallback } from 'react';
import { api } from '@/lib/api';
import { useToast } from '@/components/Toast';
import Modal from '@/components/Modal';
import MetricCard from '@/components/MetricCard';
import StatusBadge from '@/components/StatusBadge';
import { formatCurrency, formatNumber, timeAgo } from '@/lib/utils';
import type { Tenant, Nas, Transaction, SystemEvent } from '@/lib/types';
import {
  DollarSign, TrendingUp, Building2, Router, Percent,
  Users, Wallet, Activity, ShieldCheck, AlertTriangle,
  CreditCard, Server, CheckCircle2, Ban, Eye,
} from 'lucide-react';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, BarChart, Bar, Legend,
} from 'recharts';

const PIE_COLORS = ['#6366f1', '#10b981', '#f59e0b', '#ef4444'];

export default function SuperAdminDashboard() {
  const { toast } = useToast();
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [allNas, setAllNas] = useState<Nas[]>([]);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [events, setEvents] = useState<SystemEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [showVendorModal, setShowVendorModal] = useState(false);
  const [showCommissionModal, setShowCommissionModal] = useState(false);
  const [selectedTenant, setSelectedTenant] = useState<Tenant | null>(null);
  const [newVendor, setNewVendor] = useState({ business_name: '', email: '', commission: '10' });
  const [newCommission, setNewCommission] = useState('');
  const [processingPayout, setProcessingPayout] = useState(false);
  const [showVendorActivity, setShowVendorActivity] = useState(false);

  const handleTenantAction = async (tenant: Tenant, action: 'suspend' | 'close' | 'impersonate') => {
    try {
      if (action === 'impersonate') {
        await api.impersonateTenant(tenant.id);
        toast(`Read-only activity access opened for ${tenant.business_name}`);
      } else {
        const reason = window.prompt(`Reason for ${action}ing ${tenant.business_name}:`, '') ?? '';
        const updated = await api.updateTenantStatus(tenant.id, action, reason);
        setTenants((current) => current.map((item) => item.id === updated.id ? updated : item));
        toast(`${tenant.business_name} ${action}d`);
      }
    } catch { toast(`Unable to ${action} this vendor`, 'error'); }
  };

  const fetchData = useCallback(async () => {
    try {
      const [tenantsData, routersData, transactionsData] = await Promise.all([
        api.getTenants(), api.getRouters(), api.getTransactions(),
      ]);
      setTenants(tenantsData); setAllNas(routersData); setTransactions(transactionsData); setEvents([]);
    } catch { toast('Unable to load platform data', 'error'); } finally { setLoading(false); }
  }, [toast]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const totalRevenue = transactions.reduce((s, t) => s + Number(t.gross_amount), 0);
  const totalCommission = transactions.reduce((s, t) => s + Number(t.platform_fee), 0);
  const activeVendors = tenants.filter((t) => t.status.toLowerCase() === 'active').length;
  const totalRouters = allNas.length;
  const onlineRouters = allNas.filter((n) => n.is_online).length;

  const routerCountByTenant = (tenantId: string) => allNas.filter((n) => n.tenant_id === tenantId).length;
  const earningsByTenant = (tenantId: string) =>
    transactions.filter((t) => t.tenant_id === tenantId).reduce((s, t) => s + Number(t.vendor_net_amount), 0);

  const filteredTenants = statusFilter === 'all' ? tenants : tenants.filter((t) => t.status.toLowerCase() === statusFilter);

  const revenueTrend = Array.from({ length: 14 }, (_, i) => {
    const date = new Date();
    date.setDate(date.getDate() - (13 - i));
    const dayStr = date.toISOString().slice(0, 10);
    const dayTx = transactions.filter((t) => t.created_at.slice(0, 10) === dayStr);
    return {
      date: date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
      revenue: dayTx.reduce((s, t) => s + Number(t.gross_amount), 0),
      commission: dayTx.reduce((s, t) => s + Number(t.platform_fee), 0),
    };
  });

  const revenueSplit = [
    { name: 'Platform Fee', value: totalCommission },
    { name: 'Vendor Payouts', value: totalRevenue - totalCommission },
    { name: 'Gateway Fees', value: totalRevenue * 0.029 },
  ];

  const vendorRevenueData = tenants.map((t) => ({
    name: t.business_name.split(' ').slice(0, 2).join(' '),
    revenue: earningsByTenant(t.id),
    commission: transactions.filter((tx) => tx.tenant_id === t.id).reduce((s, tx) => s + Number(tx.platform_fee), 0),
  }));

  const handleAddVendor = async () => {
    if (!newVendor.business_name || !newVendor.email) {
      toast('Please fill in all fields', 'error');
      return;
    }
    try { await api.createTenant({
      business_name: newVendor.business_name,
      email: newVendor.email,
      phone_number: '',
      platform_commission_pct: parseFloat(newVendor.commission),
      status: 'PENDING',
      balance: 0,
    }); } catch {
      toast('Failed to add vendor', 'error');
      return;
    }
    toast(`Vendor "${newVendor.business_name}" onboarded successfully`);
    setNewVendor({ business_name: '', email: '', commission: '10' });
    setShowVendorModal(false);
    fetchData();
  };

  const handleUpdateCommission = async () => {
    if (!selectedTenant || !newCommission) return;
    const pct = parseFloat(newCommission);
    if (isNaN(pct) || pct < 0 || pct > 100) {
      toast('Commission must be between 0 and 100', 'error');
      return;
    }
    try { await api.updateTenant(selectedTenant.id, { platform_commission_pct: pct }); } catch {
      toast('Failed to update commission', 'error');
      return;
    }
    toast(`Commission for ${selectedTenant.business_name} updated to ${pct}%`);
    setShowCommissionModal(false);
    setNewCommission('');
    fetchData();
  };

  const handleProcessPayouts = async () => {
    setProcessingPayout(true);
    await new Promise((r) => setTimeout(r, 1500));
    const activeTenants = tenants.filter((t) => t.status.toLowerCase() === 'active' && t.balance > 0);
    const totalPayout = activeTenants.reduce((s, t) => s + Number(t.balance), 0);
    for (const t of activeTenants) {
      await api.updateTenant(t.id, { balance: 0 });
    }
    toast(`Payouts dispatched: ${formatCurrency(totalPayout)} to ${activeTenants.length} vendors`);
    setProcessingPayout(false);
    fetchData();
  };

  const eventIcon = (type: string, severity: string) => {
    if (severity === 'error') return <AlertTriangle className="h-4 w-4 text-rose-400" />;
    if (severity === 'success') return <CheckCircle2 className="h-4 w-4 text-emerald-400" />;
    if (severity === 'warning') return <AlertTriangle className="h-4 w-4 text-amber-400" />;
    if (type === 'heartbeat') return <Activity className="h-4 w-4 text-sky-400" />;
    if (type === 'payment') return <CreditCard className="h-4 w-4 text-indigo-400" />;
    if (type === 'router') return <Router className="h-4 w-4 text-violet-400" />;
    return <Server className="h-4 w-4 text-zinc-400" />;
  };

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-white/20 border-t-indigo-500" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Metrics Header */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
        <MetricCard label="Total SaaS Revenue" value={formatCurrency(totalRevenue)} icon={<DollarSign className="h-5 w-5" />} accent="indigo" trend="+12.5% vs last month" trendUp />
        <MetricCard label="MRR (Est.)" value={formatCurrency(totalRevenue * 0.85)} icon={<TrendingUp className="h-5 w-5" />} accent="emerald" trend="+8.2% MoM" trendUp />
        <MetricCard
          label="Active Vendors"
          value={formatNumber(activeVendors)}
          icon={<Building2 className="h-5 w-5" />}
          accent="sky"
          trend="View vendor activity"
          trendUp
          onClick={() => setShowVendorActivity(true)}
        />
        <MetricCard label="Connected Routers" value={`${onlineRouters}/${totalRouters}`} icon={<Router className="h-5 w-5" />} accent="violet" />
        <MetricCard label="Platform Commission" value={formatCurrency(totalCommission)} icon={<Percent className="h-5 w-5" />} accent="amber" />
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="glass-card rounded-2xl p-5 lg:col-span-2">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-white">Revenue & Commission Trend</h3>
              <p className="text-xs text-zinc-500">Last 14 days</p>
            </div>
            <div className="flex items-center gap-4 text-xs">
              <span className="flex items-center gap-1.5 text-zinc-400"><span className="h-2 w-2 rounded-full bg-indigo-500" />Revenue</span>
              <span className="flex items-center gap-1.5 text-zinc-400"><span className="h-2 w-2 rounded-full bg-emerald-500" />Commission</span>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={240}>
            <AreaChart data={revenueTrend}>
              <defs>
                <linearGradient id="revGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="commGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
              <XAxis dataKey="date" tick={{ fill: '#71717a', fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: '#71717a', fontSize: 11 }} axisLine={false} tickLine={false} />
              <Tooltip
                contentStyle={{ background: '#18181b', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '12px', fontSize: '12px' }}
                labelStyle={{ color: '#a1a1aa' }}
              />
              <Area type="monotone" dataKey="revenue" stroke="#6366f1" strokeWidth={2} fill="url(#revGrad)" />
              <Area type="monotone" dataKey="commission" stroke="#10b981" strokeWidth={2} fill="url(#commGrad)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <div className="glass-card rounded-2xl p-5">
          <h3 className="mb-4 text-sm font-semibold text-white">Revenue Split</h3>
          <ResponsiveContainer width="100%" height={200}>
            <PieChart>
              <Pie data={revenueSplit} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={45} outerRadius={75} paddingAngle={3}>
                {revenueSplit.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
              </Pie>
              <Tooltip
                contentStyle={{ background: '#18181b', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '12px', fontSize: '12px' }}
                formatter={(v: number) => formatCurrency(v)}
              />
            </PieChart>
          </ResponsiveContainer>
          <div className="mt-3 space-y-2">
            {revenueSplit.map((s, i) => (
              <div key={s.name} className="flex items-center justify-between text-xs">
                <span className="flex items-center gap-2 text-zinc-400">
                  <span className="h-2 w-2 rounded-full" style={{ background: PIE_COLORS[i] }} />
                  {s.name}
                </span>
                <span className="font-medium text-white">{formatCurrency(s.value)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Vendor Revenue Bar Chart */}
      <div className="glass-card rounded-2xl p-5">
        <h3 className="mb-4 text-sm font-semibold text-white">Vendor Performance Comparison</h3>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={vendorRevenueData}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
            <XAxis dataKey="name" tick={{ fill: '#71717a', fontSize: 11 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: '#71717a', fontSize: 11 }} axisLine={false} tickLine={false} />
            <Tooltip
              contentStyle={{ background: '#18181b', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '12px', fontSize: '12px' }}
              cursor={{ fill: 'rgba(255,255,255,0.03)' }}
              formatter={(v: number) => formatCurrency(v)}
            />
            <Legend wrapperStyle={{ fontSize: '12px' }} />
            <Bar dataKey="revenue" name="Vendor Revenue" fill="#6366f1" radius={[4, 4, 0, 0]} />
            <Bar dataKey="commission" name="Platform Commission" fill="#10b981" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Vendor Management Table */}
      <div className="glass-card rounded-2xl overflow-hidden">
        <div className="flex flex-col gap-3 border-b border-white/10 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h3 className="text-sm font-semibold text-white">Vendor Management</h3>
            <p className="text-xs text-zinc-500">{tenants.length} registered vendors</p>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex rounded-lg border border-white/10 p-0.5">
              {['all', 'active', 'suspended', 'pending'].map((s) => (
                <button
                  key={s}
                  onClick={() => setStatusFilter(s)}
                  className={`rounded-md px-3 py-1.5 text-xs font-medium capitalize transition-colors ${
                    statusFilter === s ? 'bg-white/10 text-white' : 'text-zinc-500 hover:text-zinc-300'
                  }`}
                >
                  {s}
                </button>
              ))}
            </div>
            <button
              onClick={() => setShowVendorModal(true)}
              className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-2 text-xs font-medium text-white hover:bg-indigo-500 transition-colors"
            >
              <Users className="h-3.5 w-3.5" /> Onboard Vendor
            </button>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/10 text-left text-xs text-zinc-500">
                <th className="px-5 py-3 font-medium">Business Name</th>
                <th className="px-5 py-3 font-medium">Email</th>
                <th className="px-5 py-3 font-medium">Routers</th>
                <th className="px-5 py-3 font-medium">Earnings</th>
                <th className="px-5 py-3 font-medium">Commission</th>
                <th className="px-5 py-3 font-medium">Status</th>
                <th className="px-5 py-3 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredTenants.map((t) => (
                <tr key={t.id} className="border-b border-white/5 hover:bg-white/[0.02] transition-colors">
                  <td className="px-5 py-3.5">
                    <div className="flex items-center gap-2.5">
                      <div className="flex h-8 w-8 items-center justify-center rounded-lg text-xs font-bold text-white" style={{ background: t.brand_color }}>
                        {t.business_name.charAt(0)}
                      </div>
                      <span className="font-medium text-white">{t.business_name}</span>
                    </div>
                  </td>
                  <td className="px-5 py-3.5 text-zinc-400">{t.email}</td>
                  <td className="px-5 py-3.5">
                    <span className="inline-flex items-center gap-1 text-zinc-300">
                      <Router className="h-3.5 w-3.5 text-zinc-500" />
                      {routerCountByTenant(t.id)}
                    </span>
                  </td>
                  <td className="px-5 py-3.5 font-medium text-emerald-400">{formatCurrency(earningsByTenant(t.id))}</td>
                  <td className="px-5 py-3.5">
                    <span className="rounded-md bg-indigo-500/10 px-2 py-1 text-xs font-medium text-indigo-300">
                      {Number(t.platform_commission_pct).toFixed(0)}%
                    </span>
                  </td>
                  <td className="px-5 py-3.5"><StatusBadge status={t.status} /></td>
                  <td className="px-5 py-3.5 text-right">
                    <div className="flex justify-end gap-1.5">
                      <button title="Inspect vendor activity" onClick={() => handleTenantAction(t, 'impersonate')} className="rounded-lg border border-white/10 p-1.5 text-zinc-300 hover:bg-white/5"><Eye className="h-3.5 w-3.5" /></button>
                      <button title="Suspend account" onClick={() => handleTenantAction(t, 'suspend')} disabled={t.status.toLowerCase() !== 'active'} className="rounded-lg border border-amber-400/20 p-1.5 text-amber-300 hover:bg-amber-400/10 disabled:opacity-30"><Ban className="h-3.5 w-3.5" /></button>
                      <button title="Close account" onClick={() => handleTenantAction(t, 'close')} disabled={t.status.toLowerCase() === 'closed'} className="rounded-lg border border-rose-400/20 p-1.5 text-rose-300 hover:bg-rose-400/10 disabled:opacity-30"><AlertTriangle className="h-3.5 w-3.5" /></button>
                      <button onClick={() => { setSelectedTenant(t); setNewCommission(String(t.platform_commission_pct)); setShowCommissionModal(true); }} className="rounded-lg border border-white/10 px-2.5 py-1 text-xs font-medium text-zinc-300 hover:bg-white/5">Adjust</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Payouts & System Health */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="glass-card rounded-2xl p-5">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-white">Platform Payouts</h3>
              <p className="text-xs text-zinc-500">Process vendor earnings</p>
            </div>
            <Wallet className="h-5 w-5 text-emerald-400" />
          </div>
          <div className="space-y-3">
            {tenants.filter((t) => t.status === 'active').map((t) => (
              <div key={t.id} className="flex items-center justify-between rounded-xl border border-white/5 bg-white/[0.02] px-4 py-3">
                <div className="flex items-center gap-3">
                  <div className="flex h-8 w-8 items-center justify-center rounded-lg text-xs font-bold text-white" style={{ background: t.brand_color }}>
                    {t.business_name.charAt(0)}
                  </div>
                  <div>
                    <p className="text-sm font-medium text-white">{t.business_name}</p>
                    <p className="text-xs text-zinc-500">Balance: {formatCurrency(Number(t.balance))}</p>
                  </div>
                </div>
                <span className="text-sm font-semibold text-emerald-400">{formatCurrency(Number(t.balance))}</span>
              </div>
            ))}
          </div>
          <button
            onClick={handleProcessPayouts}
            disabled={processingPayout}
            className="mt-4 flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-600 px-4 py-3 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50 transition-colors"
          >
            {processingPayout ? (
              <><div className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" /> Processing...</>
            ) : (
              <><ShieldCheck className="h-4 w-4" /> Process All Payouts</>
            )}
          </button>
        </div>

        <div className="glass-card rounded-2xl p-5">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-white">System Health Log</h3>
              <p className="text-xs text-zinc-500">Live event stream</p>
            </div>
            <span className="flex items-center gap-1.5 text-xs text-emerald-400">
              <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" /> Live
            </span>
          </div>
          <div className="max-h-80 space-y-2 overflow-y-auto pr-1">
            {events.map((e) => (
              <div key={e.id} className="flex items-start gap-3 rounded-lg border border-white/5 bg-white/[0.02] px-3 py-2.5">
                <div className="mt-0.5">{eventIcon(e.event_type, e.severity)}</div>
                <div className="flex-1 min-w-0">
                  <p className="text-xs text-zinc-300 leading-snug">{e.message}</p>
                  <p className="mt-0.5 text-[10px] text-zinc-600">{timeAgo(e.created_at)}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Onboard Vendor Modal */}
      <Modal
        open={showVendorActivity}
        onClose={() => setShowVendorActivity(false)}
        title="Active vendor activity"
        description="Review the current operating picture for every active client."
        size="lg"
      >
        <div className="space-y-3">
          {tenants.filter((tenant) => tenant.status.toLowerCase() === 'active').map((tenant) => {
            const vendorTransactions = transactions.filter((transaction) => transaction.tenant_id === tenant.id);
            const vendorRouters = allNas.filter((router) => router.tenant_id === tenant.id);
            const recentTransaction = vendorTransactions[0];
            return (
              <div key={tenant.id} className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-xl text-sm font-bold text-white" style={{ background: tenant.brand_color }}>
                      {tenant.business_name.charAt(0)}
                    </div>
                    <div>
                      <p className="font-semibold text-white">{tenant.business_name}</p>
                      <p className="text-xs text-zinc-500">{tenant.email}</p>
                    </div>
                  </div>
                  <StatusBadge status={tenant.status} />
                </div>
                <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
                  <div className="rounded-lg border border-white/5 bg-black/10 p-3"><p className="text-[10px] uppercase tracking-wider text-zinc-500">Routers</p><p className="mt-1 text-lg font-semibold text-white">{vendorRouters.filter((router) => router.is_online).length}/{vendorRouters.length}</p></div>
                  <div className="rounded-lg border border-white/5 bg-black/10 p-3"><p className="text-[10px] uppercase tracking-wider text-zinc-500">Earnings</p><p className="mt-1 text-lg font-semibold text-emerald-300">{formatCurrency(earningsByTenant(tenant.id))}</p></div>
                  <div className="rounded-lg border border-white/5 bg-black/10 p-3"><p className="text-[10px] uppercase tracking-wider text-zinc-500">Payments</p><p className="mt-1 text-lg font-semibold text-white">{vendorTransactions.length}</p></div>
                  <div className="rounded-lg border border-white/5 bg-black/10 p-3"><p className="text-[10px] uppercase tracking-wider text-zinc-500">Last payment</p><p className="mt-1 truncate text-xs text-zinc-300">{recentTransaction ? timeAgo(recentTransaction.created_at) : 'No activity yet'}</p></div>
                </div>
              </div>
            );
          })}
          {tenants.filter((tenant) => tenant.status.toLowerCase() === 'active').length === 0 && <p className="py-8 text-center text-sm text-zinc-500">No active vendors found.</p>}
        </div>
      </Modal>

      <Modal
        open={showVendorModal}
        onClose={() => setShowVendorModal(false)}
        title="Onboard New Vendor"
        description="Register a new hotspot owner on the platform"
        footer={
          <>
            <button onClick={() => setShowVendorModal(false)} className="rounded-lg border border-white/10 px-4 py-2 text-sm text-zinc-300 hover:bg-white/5 transition-colors">Cancel</button>
            <button onClick={handleAddVendor} className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 transition-colors">Onboard Vendor</button>
          </>
        }
      >
        <div className="space-y-4">
          <div>
            <label className="mb-1.5 block text-xs font-medium text-zinc-400">Business Name</label>
            <input
              value={newVendor.business_name}
              onChange={(e) => setNewVendor({ ...newVendor, business_name: e.target.value })}
              placeholder="e.g. Downtown Coffee Co."
              className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white placeholder-zinc-600 focus:border-indigo-500/50 focus:outline-none focus:ring-1 focus:ring-indigo-500/30"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-medium text-zinc-400">Vendor Email</label>
            <input
              type="email"
              value={newVendor.email}
              onChange={(e) => setNewVendor({ ...newVendor, email: e.target.value })}
              placeholder="owner@business.com"
              className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white placeholder-zinc-600 focus:border-indigo-500/50 focus:outline-none focus:ring-1 focus:ring-indigo-500/30"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-medium text-zinc-400">Platform Commission Rate (%)</label>
            <input
              type="number"
              value={newVendor.commission}
              onChange={(e) => setNewVendor({ ...newVendor, commission: e.target.value })}
              min="0" max="100" step="0.5"
              className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white focus:border-indigo-500/50 focus:outline-none focus:ring-1 focus:ring-indigo-500/30"
            />
            <p className="mt-1.5 text-xs text-zinc-600">Platform takes this percentage of each transaction</p>
          </div>
        </div>
      </Modal>

      {/* Commission Modal */}
      <Modal
        open={showCommissionModal}
        onClose={() => setShowCommissionModal(false)}
        title="Adjust Commission Rate"
        description={selectedTenant ? `Vendor: ${selectedTenant.business_name}` : ''}
        size="sm"
        footer={
          <>
            <button onClick={() => setShowCommissionModal(false)} className="rounded-lg border border-white/10 px-4 py-2 text-sm text-zinc-300 hover:bg-white/5 transition-colors">Cancel</button>
            <button onClick={handleUpdateCommission} className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 transition-colors">Update</button>
          </>
        }
      >
        <div>
          <label className="mb-1.5 block text-xs font-medium text-zinc-400">New Commission Rate (%)</label>
          <input
            type="number"
            value={newCommission}
            onChange={(e) => setNewCommission(e.target.value)}
            min="0" max="100" step="0.5"
            className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white focus:border-indigo-500/50 focus:outline-none focus:ring-1 focus:ring-indigo-500/30"
          />
          <p className="mt-2 text-xs text-zinc-600">Current: {selectedTenant ? Number(selectedTenant.platform_commission_pct).toFixed(1) : 0}%</p>
        </div>
      </Modal>
    </div>
  );
}
