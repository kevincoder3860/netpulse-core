import { useState, useEffect, useCallback, type FormEvent } from 'react';
import { api } from '@/lib/api';
import { ToastProvider } from '@/components/Toast';
import SuperAdminDashboard from '@/components/SuperAdminDashboard';
import VendorDashboard from '@/components/VendorDashboard';
import CaptivePortal from '@/components/CaptivePortal';
import HotspotOperations from '@/components/HotspotOperations';
import type { Tenant, Role } from '@/lib/types';
import {
  ShieldCheck, Building2, Smartphone, Activity,
  ChevronDown, Radio, Server, Menu, Bell, Search, LogOut, Wifi,
} from 'lucide-react';

function AuthScreen({ onAuthenticated }: { onAuthenticated: () => void }) {
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [businessName, setBusinessName] = useState('');
  const [phoneNumber, setPhoneNumber] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError('');
    try {
      if (mode === 'register') {
        await api.register({ email, password, business_name: businessName, phone_number: phoneNumber });
      } else {
        await api.signIn(username, password);
      }
      onAuthenticated();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Authentication failed');
    }
    finally { setBusy(false); }
  };

  return <div className="flex min-h-screen items-center justify-center bg-[#071014] p-6">
    <form onSubmit={submit} className="w-full max-w-md rounded-3xl border border-cyan-200/10 bg-[#0b2024] p-8 shadow-2xl">
      <div className="mb-8 flex items-center gap-3"><div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-cyan-400 text-[#071014]"><Radio className="h-5 w-5" /></div><div><p className="font-bold text-white">NetPulse Cloud</p><p className="text-xs text-zinc-500">Network operations suite</p></div></div>
      <h1 className="text-2xl font-bold text-white">{mode === 'login' ? 'Welcome back' : 'Create your workspace'}</h1>
      <p className="mt-2 text-sm text-zinc-500">{mode === 'login' ? 'Sign in to manage your hotspot network.' : 'Create an account to get started.'}</p>
      <div className="mt-6 space-y-4">
        {mode === 'register' && <>
          <input required type="text" value={businessName} onChange={(e) => setBusinessName(e.target.value)} placeholder="Business name" className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white outline-none focus:border-cyan-300/50" />
          <input required type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Work email" className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white outline-none focus:border-cyan-300/50" />
          <input required type="tel" value={phoneNumber} onChange={(e) => setPhoneNumber(e.target.value)} placeholder="Phone number" className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white outline-none focus:border-cyan-300/50" />
        </>}
        {mode === 'login' && <input required value={username} onChange={(e) => setUsername(e.target.value)} placeholder="Username" className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white outline-none focus:border-cyan-300/50" />}
        <input required minLength={8} type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Password" className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white outline-none focus:border-cyan-300/50" />
      </div>
      {error && <div className={`mt-4 rounded-xl border px-4 py-3 text-sm ${/suspended|closed/i.test(error) ? 'border-amber-300/20 bg-amber-300/10 text-amber-200' : 'border-rose-300/20 bg-rose-300/10 text-rose-200'}`}>{error}</div>}
      <button disabled={busy} className="mt-6 w-full rounded-xl bg-cyan-300 px-4 py-3 font-semibold text-[#071014] transition hover:bg-cyan-200 disabled:opacity-50">{busy ? 'Please wait...' : mode === 'login' ? 'Sign in' : 'Create account'}</button>
      <button type="button" onClick={() => setMode(mode === 'login' ? 'register' : 'login')} className="mt-4 w-full text-sm text-zinc-400 hover:text-white">{mode === 'login' ? 'Create an account' : 'Already have an account? Sign in'}</button>
    </form>
  </div>;
}

function AppContent() {
  const [role, setRole] = useState<Role>(() => api.getAuthClaims()?.role === 'SUPERADMIN' ? 'superadmin' : 'vendor');
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [selectedTenantId, setSelectedTenantId] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [vendorNav, setVendorNav] = useState<'dashboard' | 'operations' | 'portal'>('dashboard');
  const [authenticated, setAuthenticated] = useState(api.isAuthenticated());

  const fetchTenants = useCallback(async () => {
    if (!api.isAuthenticated()) { setLoading(false); return; }
    try {
      const t = await api.getTenants();
      setTenants(t);
      if (t.length > 0 && !selectedTenantId) setSelectedTenantId(t[0].id);
    } catch {
      api.signOut();
      setAuthenticated(false);
    } finally { setLoading(false); }
  }, [selectedTenantId]);

  useEffect(() => { fetchTenants(); }, [fetchTenants]);

  useEffect(() => {
    const handleSessionExpired = () => { setAuthenticated(false); setTenants([]); setSelectedTenantId(''); };
    window.addEventListener('np:session-expired', handleSessionExpired);
    return () => window.removeEventListener('np:session-expired', handleSessionExpired);
  }, []);

  const setAuthenticatedRole = () => {
    setRole(api.getAuthClaims()?.role === 'SUPERADMIN' ? 'superadmin' : 'vendor');
    setAuthenticated(true);
    setLoading(true);
    fetchTenants();
  };

  const handleSignOut = () => {
    api.signOut();
    setAuthenticated(false);
    setTenants([]);
    setSelectedTenantId('');
  };

  if (!authenticated) return <AuthScreen onAuthenticated={setAuthenticatedRole} />;

  const selectedTenant = tenants.find((t) => t.id === selectedTenantId) || tenants[0] || null;

  const navItems = [
    { id: 'superadmin' as Role, label: 'Command center', icon: ShieldCheck, desc: 'Platform overview' },
    { id: 'vendor' as Role, label: 'Vendor workspace', icon: Building2, desc: 'Manage your network' },
    { id: 'enduser' as Role, label: 'Customer portal', icon: Smartphone, desc: 'Preview the experience' },
  ];

  const vendorNavItems = [
    { id: 'dashboard' as const, label: 'Dashboard', icon: Activity },
    { id: 'operations' as const, label: 'Hotspot Management', icon: Wifi },
    { id: 'portal' as const, label: 'Portal Preview', icon: Smartphone },
  ];

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-zinc-950">
        <div className="flex flex-col items-center gap-3">
          <div className="h-10 w-10 animate-spin rounded-full border-2 border-white/20 border-t-indigo-500" />
          <p className="text-sm text-zinc-500">Syncing your workspace...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen bg-zinc-950 text-white overflow-hidden">
      {/* Sidebar */}
      <aside className={`fixed lg:static inset-y-0 left-0 z-40 flex w-64 flex-col border-r border-white/10 bg-zinc-950/95 backdrop-blur-xl transition-transform duration-300 ${sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}`}>
        {/* Logo */}
        <div className="flex items-center gap-3 border-b border-white/10 px-6 py-5">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-emerald-500">
            <Radio className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="text-base font-bold text-white leading-tight">NetPulse</h1>
            <p className="text-[10px] font-medium uppercase tracking-wider text-zinc-500">SaaS Platform</p>
          </div>
        </div>

        {/* Role Switcher */}
        <div className="border-b border-white/10 px-4 py-4">
          <p className="mb-2 px-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-zinc-600">Workspaces</p>
          <div className="space-y-1">
            {navItems.filter((item) => item.id === role).map((item) => (
              <button
                key={item.id}
                onClick={() => { setSidebarOpen(false); setVendorNav('dashboard'); }}
                className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 transition-colors ${
                  role === item.id ? 'bg-white/10 text-white' : 'text-zinc-500 hover:bg-white/5 hover:text-zinc-300'
                }`}
              >
                <item.icon className="h-4 w-4" />
                <div className="text-left">
                  <p className="text-sm font-medium">{item.label}</p>
                  <p className="text-[10px] text-zinc-600">{item.desc}</p>
                </div>
                {role === item.id && <div className="ml-auto h-1.5 w-1.5 rounded-full bg-indigo-400" />}
              </button>
            ))}
          </div>
        </div>

        {/* Vendor selector (shown for vendor & enduser roles) */}
        {(role === 'vendor' || role === 'enduser') && (
          <div className="border-b border-white/10 px-4 py-4">
            <p className="mb-2 px-2 text-[10px] font-semibold uppercase tracking-wider text-zinc-600">Active Vendor</p>
            <div className="relative">
              <select
                value={selectedTenantId}
                onChange={(e) => setSelectedTenantId(e.target.value)}
                className="w-full appearance-none rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 pr-8 text-sm text-white focus:border-indigo-500/50 focus:outline-none"
              >
                {tenants.map((t) => (
                  <option key={t.id} value={t.id} className="bg-zinc-900">{t.business_name}</option>
                ))}
              </select>
              <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500" />
            </div>
          </div>
        )}

        {/* Vendor sub-nav */}
        {role === 'vendor' && selectedTenant && (
          <div className="border-b border-white/10 px-4 py-4">
            <p className="mb-2 px-2 text-[10px] font-semibold uppercase tracking-wider text-zinc-600">Vendor Views</p>
            <div className="space-y-1">
              {vendorNavItems.map((item) => (
                <button
                  key={item.id}
                  onClick={() => setVendorNav(item.id)}
                  className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition-colors ${
                    vendorNav === item.id ? 'bg-white/10 text-white' : 'text-zinc-500 hover:bg-white/5 hover:text-zinc-300'
                  }`}
                >
                  <item.icon className="h-4 w-4" />
                  {item.label}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Status footer */}
        <div className="mt-auto border-t border-white/10 px-4 py-4">
          <div className="flex items-center gap-2 rounded-xl border border-emerald-500/20 bg-emerald-500/5 px-3 py-2.5">
            <div className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
            <span className="text-xs font-medium text-emerald-300">All Systems Operational</span>
          </div>
          <p className="mt-2 px-2 text-[10px] text-zinc-600">NetPulse Cloud · Operations suite</p>
        </div>
      </aside>

      {/* Mobile overlay */}
      {sidebarOpen && (
        <div className="fixed inset-0 z-30 bg-black/60 backdrop-blur-sm lg:hidden" onClick={() => setSidebarOpen(false)} />
      )}

      {/* Main content */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Top bar */}
        <header className="flex items-center justify-between border-b border-white/10 px-6 py-3.5">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="rounded-lg border border-white/10 p-2 text-zinc-400 hover:bg-white/5 lg:hidden"
            >
              <Menu className="h-4 w-4" />
            </button>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-semibold tracking-tight text-white">
                  {role === 'superadmin' ? 'Command center' :
                   role === 'vendor' ? (vendorNav === 'portal' ? 'Portal preview' : vendorNav === 'operations' ? 'Hotspot management' : 'Vendor workspace') :
                   'Customer portal'}
                </h2>
                <span className="hidden rounded-full border border-cyan-400/20 bg-cyan-400/10 px-2 py-0.5 text-[10px] font-medium text-cyan-200 sm:inline-flex">Live workspace</span>
              </div>
              <p className="text-xs text-zinc-500">
                {role === 'superadmin' ? 'Monitoring all vendors across the platform' :
                 role === 'vendor' && selectedTenant ? selectedTenant.business_name :
                 role === 'enduser' && selectedTenant ? `Previewing: ${selectedTenant.business_name}` : ''}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {role === 'superadmin' && (
              <div className="hidden items-center gap-4 sm:flex">
                <div className="flex items-center gap-1.5 text-xs text-zinc-500">
                  <Server className="h-3.5 w-3.5" /> 12 Routers
                </div>
                <div className="flex items-center gap-1.5 text-xs text-zinc-500">
                  <Building2 className="h-3.5 w-3.5" /> {tenants.length} Vendors
                </div>
                <div className="flex items-center gap-1.5 text-xs text-emerald-400">
                  <div className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" /> Live
                </div>
              </div>
            )}
            <button className="hidden rounded-lg border border-white/10 p-2 text-zinc-400 transition hover:border-white/20 hover:bg-white/5 hover:text-white sm:block" aria-label="Search">
              <Search className="h-4 w-4" />
            </button>
            <button className="hidden rounded-lg border border-white/10 p-2 text-zinc-400 transition hover:border-white/20 hover:bg-white/5 hover:text-white sm:block" aria-label="Notifications">
              <Bell className="h-4 w-4" />
            </button>
            <button
              onClick={handleSignOut}
              title="Sign out"
              aria-label="Sign out"
              className="rounded-lg border border-rose-400/20 p-2 text-rose-300 transition hover:border-rose-400/40 hover:bg-rose-400/10"
            >
              <LogOut className="h-4 w-4" />
            </button>
            <div className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.06] px-2.5 py-1.5">
              <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500 to-emerald-500 text-xs font-bold text-white">
                {role === 'superadmin' ? 'SA' : role === 'vendor' ? 'V' : 'U'}
              </div>
              <span className="hidden text-xs font-medium text-white capitalize sm:inline">
                {role === 'superadmin' ? 'SuperAdmin' : role === 'vendor' ? 'Vendor' : 'End-User'}
              </span>
            </div>
          </div>
        </header>

        {/* Dashboard content */}
        <main className="app-main flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8">
          {role === 'superadmin' && <SuperAdminDashboard />}
          {role === 'vendor' && selectedTenant && vendorNav === 'dashboard' && (
            <VendorDashboard tenant={selectedTenant} onBrandingChange={fetchTenants} />
          )}
          {role === 'vendor' && selectedTenant && vendorNav === 'operations' && (
            <HotspotOperations tenant={selectedTenant} />
          )}
          {role === 'vendor' && selectedTenant && vendorNav === 'portal' && (
            <CaptivePortal tenant={selectedTenant} />
          )}
          {role === 'enduser' && selectedTenant && (
            <CaptivePortal tenant={selectedTenant} />
          )}
        </main>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <ToastProvider>
      <AppContent />
    </ToastProvider>
  );
}
