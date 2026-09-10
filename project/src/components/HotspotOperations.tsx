import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { api, type AnalyticsData, type RechargeRecord, type VoucherRecord } from '@/lib/api';
import { useTelemetry } from '@/hooks/useTelemetry';
import { formatCurrency } from '@/lib/utils';
import { Activity, BarChart3, CalendarDays, CircleDollarSign, Download, Gauge, Plus, Router, Ticket, Trash2, Users, Wifi } from 'lucide-react';
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { Tenant } from '@/lib/types';

interface Props { tenant: Tenant; }
type Tab = 'overview' | 'clients' | 'vouchers' | 'recharges' | 'services' | 'billing';

const tabs: { id: Tab; label: string; icon: typeof Activity }[] = [
  { id: 'overview', label: 'Dashboard', icon: Activity }, { id: 'clients', label: 'Hotspot Clients', icon: Users },
  { id: 'vouchers', label: 'Prepaid Vouchers', icon: Ticket }, { id: 'recharges', label: 'Recharges', icon: CircleDollarSign },
  { id: 'services', label: 'Plans & Profiles', icon: Gauge }, { id: 'billing', label: 'M-Pesa & Commissions', icon: BarChart3 },
];

function Metric({ label, value, icon: Icon, tone = 'cyan' }: { label: string; value: string; icon: typeof Activity; tone?: string }) {
  return <div className={`rounded-2xl border border-${tone}-400/20 bg-${tone}-400/[0.08] p-5`}><div className="flex items-center justify-between"><p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-zinc-400">{label}</p><Icon className={`h-5 w-5 text-${tone}-300`} /></div><p className="mt-3 text-2xl font-semibold text-white">{value}</p></div>;
}

export default function HotspotOperations({ tenant }: Props) {
  const [tab, setTab] = useState<Tab>('overview');
  const [analytics, setAnalytics] = useState<AnalyticsData | null>(null);
  const [vouchers, setVouchers] = useState<VoucherRecord[]>([]);
  const [recharges, setRecharges] = useState<RechargeRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [voucherCount, setVoucherCount] = useState('25');
  const [generating, setGenerating] = useState(false);
  const { telemetryData, trafficSamples, connected } = useTelemetry(tenant.id);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [analyticsData, voucherData, rechargeData] = await Promise.all([
        api.getAnalytics(tenant.id),
        api.getVouchers(tenant.id),
        api.getRecharges(tenant.id),
      ]);
      setAnalytics(analyticsData);
      setVouchers(voucherData);
      setRecharges(rechargeData);
    } finally {
      setLoading(false);
    }
  }, [tenant.id]);

  useEffect(() => {
    void load();
  }, [load]);

  const generate = async () => {
    setGenerating(true);
    try { const created = await api.generateVouchers({ tenant: tenant.id, count: Number(voucherCount) || 1, valid_days: 30 }); setVouchers((items) => [...created, ...items]); }
    finally { setGenerating(false); }
  };
  const deleteUsed = async () => { await api.deleteUsedVouchers(); setVouchers((items) => items.filter((item) => item.status !== 'USED')); };

  if (loading || !analytics) return <div className="flex min-h-[50vh] items-center justify-center"><div className="h-8 w-8 animate-spin rounded-full border-2 border-white/10 border-t-cyan-300" /></div>;

  const liveChart = trafficSamples.map((sample) => ({
    time: new Date(sample.timestamp).toLocaleTimeString([], { minute: '2-digit', second: '2-digit' }),
    tx: sample.tx_kbps,
    rx: sample.rx_kbps,
  }));
  const fallbackChart = analytics.traffic.map((item) => ({
    time: new Date(item.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    tx: Math.round(item.tx_bytes / 1024),
    rx: Math.round(item.rx_bytes / 1024),
  }));
  const chart = liveChart.length > 0 ? liveChart : fallbackChart;

  const healthSource = telemetryData ?? {
    server_cpu: analytics.health.server_cpu,
    mikrotik_cpu: analytics.health.mikrotik_cpu,
    memory: analytics.health.memory,
    disk: analytics.health.disk,
    router_memory: analytics.health.router_memory,
  };
  const healthMeters = [
    { label: 'Server CPU', value: healthSource.server_cpu },
    { label: 'MikroTik CPU', value: healthSource.mikrotik_cpu },
    { label: 'Server memory', value: healthSource.memory },
    { label: 'Server disk', value: healthSource.disk },
    { label: 'Router memory', value: healthSource.router_memory },
  ];
  const hotspotStatus = telemetryData?.hotspot_status ?? analytics.hotspot_status;

  return <div className="space-y-6">
    <div className="flex flex-col gap-4 border-b border-white/10 pb-5 lg:flex-row lg:items-end lg:justify-between"><div><p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300">Hotspot management</p><h1 className="mt-2 text-3xl font-semibold tracking-tight text-white">{tenant.business_name}</h1><p className="mt-1 text-sm text-zinc-500">Clients, access, traffic, and prepaid operations</p></div><div className={`flex items-center gap-2 text-xs ${connected ? 'text-emerald-300' : 'text-zinc-500'}`}><span className={`h-2 w-2 rounded-full ${connected ? 'animate-pulse bg-emerald-300' : 'bg-zinc-500'}`} /> {connected ? 'Live WebSocket stream' : 'Connecting telemetry…'}</div></div>
    <div className="flex gap-1 overflow-x-auto rounded-xl border border-white/10 bg-white/[0.02] p-1">{tabs.map(({ id, label, icon: Icon }) => <button key={id} onClick={() => setTab(id)} className={`flex shrink-0 items-center gap-2 rounded-lg px-3 py-2 text-xs font-medium ${tab === id ? 'bg-cyan-300 text-[#071014]' : 'text-zinc-400 hover:bg-white/5 hover:text-white'}`}><Icon className="h-3.5 w-3.5" />{label}</button>)}</div>

    {tab === 'overview' && <div className="space-y-6"><div className="grid grid-cols-2 gap-3 xl:grid-cols-4"><Metric label="Income today" value={formatCurrency(Number(telemetryData?.income_today ?? analytics.income_today))} icon={CircleDollarSign} tone="emerald" /><Metric label="Income this month" value={formatCurrency(Number(telemetryData?.income_month ?? analytics.income_month))} icon={BarChart3} tone="cyan" /><Metric label="Users active" value={String(analytics.active_users)} icon={Users} tone="sky" /><Metric label="Total users" value={String(analytics.total_users)} icon={Wifi} tone="amber" /></div><div className="grid gap-4 lg:grid-cols-[1.4fr_0.6fr]"><div className="glass-card rounded-2xl p-5"><div className="mb-5 flex items-center justify-between"><div><h2 className="text-sm font-semibold text-white">Live network traffic</h2><p className="text-xs text-zinc-500">TX/RX throughput over WebSocket</p></div><Activity className="h-5 w-5 text-cyan-300" /></div><ResponsiveContainer width="100%" height={260}><AreaChart data={chart}><defs><linearGradient id="tx" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#2dd4bf" stopOpacity=".35" /><stop offset="100%" stopColor="#2dd4bf" stopOpacity="0" /></linearGradient><linearGradient id="rx" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#38bdf8" stopOpacity=".3" /><stop offset="100%" stopColor="#38bdf8" stopOpacity="0" /></linearGradient></defs><CartesianGrid stroke="rgba(255,255,255,.06)" /><XAxis dataKey="time" tick={{ fill: '#71717a', fontSize: 10 }} /><YAxis tick={{ fill: '#71717a', fontSize: 10 }} /><Tooltip contentStyle={{ background: '#10252a', border: '1px solid rgba(255,255,255,.1)' }} /><Area dataKey="tx" stroke="#2dd4bf" fill="url(#tx)" /><Area dataKey="rx" stroke="#38bdf8" fill="url(#rx)" /></AreaChart></ResponsiveContainer></div><div className="space-y-4"><div className="glass-card rounded-2xl p-5"><h2 className="text-sm font-semibold text-white">Hotspot status</h2><div className="mt-4 grid grid-cols-3 gap-2 text-center">{[['Active', hotspotStatus.active], ['Inactive', hotspotStatus.inactive], ['Total', hotspotStatus.total]].map(([label, value]) => <div key={String(label)} className="rounded-xl bg-white/[0.04] p-3"><p className="text-xl font-semibold text-white">{value}</p><p className="mt-1 text-[10px] text-zinc-500">{label}</p></div>)}</div></div><div className="glass-card rounded-2xl p-5"><h2 className="text-sm font-semibold text-white">Router & server health</h2><div className="mt-4 space-y-3">{healthMeters.map(({ label, value }) => <div key={label}><div className="mb-1 flex justify-between text-xs text-zinc-400"><span>{label}</span><span>{Number(value).toFixed(1)}%</span></div><div className="h-1.5 rounded-full bg-white/10"><div className="h-1.5 rounded-full bg-cyan-300" style={{ width: `${Math.min(Number(value), 100)}%` }} /></div></div>)}</div></div></div></div></div>}

    {tab === 'clients' && <div className="glass-card rounded-2xl p-5"><div className="mb-5 flex items-center justify-between"><div><h2 className="text-sm font-semibold text-white">Top downloaders</h2><p className="text-xs text-zinc-500">Client activity across the last 30 days</p></div><CalendarDays className="h-5 w-5 text-cyan-300" /></div><div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead className="text-xs text-zinc-500"><tr><th className="pb-3">MAC address</th><th className="pb-3">Upload</th><th className="pb-3">Download</th></tr></thead><tbody>{analytics.top_downloaders.map((client) => <tr key={client.mac_address} className="border-t border-white/5"><td className="py-3 font-mono text-xs text-white">{client.mac_address}</td><td className="py-3 text-zinc-400">{formatBytes(client.upload)}</td><td className="py-3 font-medium text-cyan-300">{formatBytes(client.download)}</td></tr>)}</tbody></table></div><div className="mt-6 flex flex-wrap gap-2">{analytics.activity_calendar.map((day) => <div key={day.activity_date} title={`${day.activity_date}: ${day.users} users`} className="h-7 w-7 rounded-md bg-cyan-300/20 text-center text-[9px] leading-7 text-cyan-200">{day.users}</div>)}</div></div>}

    {tab === 'vouchers' && <div className="glass-card overflow-hidden rounded-2xl"><div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 p-5"><div><h2 className="text-sm font-semibold text-white">Prepaid vouchers</h2><p className="text-xs text-zinc-500">Generate, print, and manage prepaid access</p></div><div className="flex gap-2"><input value={voucherCount} onChange={(e) => setVoucherCount(e.target.value)} type="number" min="1" max="1000" className="w-20 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs text-white" /><button onClick={generate} disabled={generating} className="flex items-center gap-2 rounded-lg bg-cyan-300 px-3 py-2 text-xs font-semibold text-[#071014]"><Plus className="h-3.5 w-3.5" />{generating ? 'Generating...' : 'Add vouchers'}</button><button onClick={deleteUsed} className="flex items-center gap-2 rounded-lg border border-rose-400/30 px-3 py-2 text-xs text-rose-300"><Trash2 className="h-3.5 w-3.5" />Delete used</button><button onClick={() => window.print()} className="flex items-center gap-2 rounded-lg border border-white/10 px-3 py-2 text-xs text-zinc-300"><Download className="h-3.5 w-3.5" />Print</button></div></div><TableWrap><table className="w-full text-left text-sm"><thead className="text-xs text-zinc-500"><tr><th>Code</th><th>Status</th><th>Assigned MAC</th><th>Created</th><th>Expires</th></tr></thead><tbody>{vouchers.map((voucher) => <tr key={voucher.id} className="border-t border-white/5"><td className="py-3 font-mono text-cyan-300">{voucher.code}</td><td className="py-3"><span className={`rounded-full px-2 py-1 text-[10px] ${voucher.status === 'USED' ? 'bg-rose-400/10 text-rose-300' : 'bg-emerald-400/10 text-emerald-300'}`}>{voucher.status}</span></td><td className="py-3 font-mono text-xs text-zinc-400">{voucher.assigned_mac || '—'}</td><td className="py-3 text-xs text-zinc-500">{new Date(voucher.created_at).toLocaleDateString()}</td><td className="py-3 text-xs text-zinc-500">{voucher.expires_at ? new Date(voucher.expires_at).toLocaleDateString() : '—'}</td></tr>)}</tbody></table></TableWrap></div>}

    {tab === 'recharges' && <div className="glass-card overflow-hidden rounded-2xl p-5"><h2 className="mb-5 text-sm font-semibold text-white">All prepaid recharges</h2><TableWrap><table className="w-full text-left text-sm"><thead className="text-xs text-zinc-500"><tr><th>MAC / Username</th><th>Plan</th><th>Type</th><th>Expires</th><th>Method</th><th>Router</th><th>Status</th></tr></thead><tbody>{recharges.map((item) => <tr key={item.id} className="border-t border-white/5"><td className="py-3 font-mono text-xs text-white">{item.mac_address || item.username}</td><td className="py-3 text-zinc-300">{item.plan_name || '—'}</td><td className="py-3 text-cyan-300">Hotspot</td><td className="py-3 text-xs text-zinc-500">{item.expires_at ? new Date(item.expires_at).toLocaleString() : '—'}</td><td className="py-3 text-xs text-zinc-400">{item.method}</td><td className="py-3 text-xs text-zinc-400">{item.router_name || '—'}</td><td className="py-3"><span className="rounded-full bg-emerald-400/10 px-2 py-1 text-[10px] text-emerald-300">{item.status}</span></td></tr>)}</tbody></table></TableWrap></div>}

    {tab === 'services' && <div className="grid gap-4 md:grid-cols-2"><div className="glass-card rounded-2xl p-5"><h2 className="text-sm font-semibold text-white">Hotspot plans</h2><p className="mt-1 text-xs text-zinc-500">Price, duration, and speed profiles are managed in Vendor workspace.</p><button onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })} className="mt-5 flex items-center gap-2 rounded-lg border border-white/10 px-3 py-2 text-xs text-zinc-300"><Router className="h-3.5 w-3.5" />Open plan manager</button></div><div className="glass-card rounded-2xl p-5"><h2 className="text-sm font-semibold text-white">Burst & FUP profiles</h2><p className="mt-1 text-xs text-zinc-500">Bandwidth bursts and fair usage controls are ready for profile configuration.</p><div className="mt-5 flex gap-2"><span className="rounded-full bg-cyan-300/10 px-2 py-1 text-[10px] text-cyan-200">Burst profiles API</span><span className="rounded-full bg-amber-300/10 px-2 py-1 text-[10px] text-amber-200">FUP profiles API</span></div></div></div>}

    {tab === 'billing' && <div className="grid gap-4 md:grid-cols-2"><div className="glass-card rounded-2xl p-5"><h2 className="text-sm font-semibold text-white">M-Pesa operations</h2><p className="mt-1 text-xs text-zinc-500">Transactions and status lookup remain available in the transaction ledger.</p><div className="mt-5 grid grid-cols-2 gap-2"><div className="rounded-xl bg-white/[0.04] p-4"><p className="text-2xl font-semibold text-white">{formatCurrency(Number(telemetryData?.income_month ?? analytics.income_month))}</p><p className="text-xs text-zinc-500">This month</p></div><div className="rounded-xl bg-white/[0.04] p-4"><p className="text-2xl font-semibold text-white">{vouchers.length}</p><p className="text-xs text-zinc-500">Vouchers issued</p></div></div></div><div className="glass-card rounded-2xl p-5"><h2 className="text-sm font-semibold text-white">Sales commissions</h2><p className="mt-1 text-xs text-zinc-500">Sales agents and commission records are available through the billing API.</p><button className="mt-5 rounded-lg border border-white/10 px-3 py-2 text-xs text-zinc-300">View commission records</button></div></div>}
  </div>;
}

function TableWrap({ children }: { children: ReactNode }) { return <div className="overflow-x-auto [&_table]:min-w-[680px] [&_th]:pb-3 [&_th]:font-medium [&_td]:pr-4" >{children}</div>; }
function formatBytes(value: number) { if (value < 1024) return `${value} B`; if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KB`; if (value < 1024 ** 3) return `${(value / 1024 ** 2).toFixed(1)} MB`; return `${(value / 1024 ** 3).toFixed(1)} GB`; }
