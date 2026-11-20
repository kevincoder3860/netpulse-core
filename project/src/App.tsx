import { useState, useEffect, useCallback, type FormEvent } from 'react';
import { BrowserRouter, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { api } from '@/lib/api';
import { ToastProvider } from '@/components/Toast';
import SuperAdminDashboard from '@/components/SuperAdminDashboard';
import VendorDashboard from '@/components/VendorDashboard';
import CustomerPortal from '@/components/CustomerPortal';
import type { Tenant, Role } from '@/lib/types';
import {
  ShieldCheck, Building2, Smartphone, ChevronDown, Radio, Menu, LogOut,
  Globe,
} from 'lucide-react';

const rolePaths: Record<Role, string> = {
  superadmin: '/superadmin',
  vendor: '/vendor',
  enduser: '/customer',
};

function roleForPath(path: string): Role {
  if (path.startsWith(rolePaths.superadmin)) return 'superadmin';
  if (path.startsWith(rolePaths.enduser)) return 'enduser';
  return 'vendor';
}

function roleForClaims(): Role {
  const claim = api.getAuthClaims()?.role;
  if (claim === 'SUPERADMIN') return 'superadmin';
  if (claim === 'CUSTOMER') return 'enduser';
  return 'vendor';
}

function AuthScreen({ onAuthenticated }: { onAuthenticated: () => void }) {
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [loginIdentifier, setLoginIdentifier] = useState('');
  const [email, setEmail] = useState('');
  const [businessName, setBusinessName] = useState('');
  const [phoneNumber, setPhoneNumber] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      if (mode === 'register') {
        await api.register({ email, password, business_name: businessName, phone_number: phoneNumber });
      } else {
        await api.signIn(loginIdentifier, password);
      }
      onAuthenticated();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Authentication failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#071014] p-6">
      <form onSubmit={submit} className="w-full max-w-md rounded-3xl border border-cyan-200/10 bg-[#0b2024] p-8 shadow-2xl">
        <div className="mb-8 flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-cyan-400 text-[#071014]">
            <Radio className="h-5 w-5" />
          </div>
          <div>
            <p className="font-bold text-white">NetPulse Cloud</p>
            <p className="text-xs text-zinc-400">Network operations & billing suite</p>
          </div>
        </div>
        <h1 className="text-2xl font-bold text-white">{mode === 'login' ? 'Welcome back' : 'Create your workspace'}</h1>
        <p className="mt-2 text-sm text-zinc-400">{mode === 'login' ? 'Sign in to manage your hotspot & ISP network.' : 'Create an account to get started.'}</p>
        <div className="mt-6 space-y-4">
          {mode === 'register' && (
            <>
              <input required type="text" value={businessName} onChange={(e) => setBusinessName(e.target.value)} placeholder="Business name" className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white outline-none focus:border-cyan-300/50" />
              <input required type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Work email" className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white outline-none focus:border-cyan-300/50" />
              <input required type="tel" value={phoneNumber} onChange={(e) => setPhoneNumber(e.target.value)} placeholder="Phone number (254...)" className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white outline-none focus:border-cyan-300/50" />
            </>
          )}
          {mode === 'login' && <input required value={loginIdentifier} onChange={(e) => setLoginIdentifier(e.target.value)} placeholder="Email or username" className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white outline-none focus:border-cyan-300/50" />}
          <input required minLength={8} type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Password" className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white outline-none focus:border-cyan-300/50" />
        </div>
        {error && <div className={`mt-4 rounded-xl border px-4 py-3 text-sm ${/suspended|closed/i.test(error) ? 'border-amber-300/20 bg-amber-300/10 text-amber-200' : 'border-rose-300/20 bg-rose-300/10 text-rose-200'}`}>{error}</div>}
        <button disabled={busy} className="mt-6 w-full rounded-xl bg-cyan-300 px-4 py-3 font-semibold text-[#071014] transition hover:bg-cyan-200 disabled:opacity-50">{busy ? 'Please wait...' : mode === 'login' ? 'Sign in' : 'Create account'}</button>
        <button type="button" onClick={() => setMode(mode === 'login' ? 'register' : 'login')} className="mt-4 w-full text-sm text-zinc-400 hover:text-white">{mode === 'login' ? 'Create an account' : 'Already have an account? Sign in'}</button>
      </form>
    </div>
  );
}

function AppContent() {
  const location = useLocation();
  const navigate = useNavigate();
  const [role, setRole] = useState<Role>(() => roleForPath(window.location.pathname));
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [selectedTenantId, setSelectedTenantId] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [authenticated, setAuthenticated] = useState(api.isAuthenticated());

  useEffect(() => {
    const requestedRole = roleForPath(location.pathname);
    const authorizedRole = roleForClaims();
    if (requestedRole !== authorizedRole) {
      setRole(authorizedRole);
      navigate(rolePaths[authorizedRole], { replace: true });
      return;
    }
    setRole(requestedRole);
  }, [location.pathname, navigate]);

  const fetchTenants = useCallback(async () => {
    if (!api.isAuthenticated()) {
      setLoading(false);
      return;
    }
    try {
      const t = await api.getTenants();
      setTenants(t);
      if (t.length > 0 && !selectedTenantId) setSelectedTenantId(t[0].id);
    } catch {
      api.signOut();
      setAuthenticated(false);
    } finally {
      setLoading(false);
    }
  }, [selectedTenantId]);

  useEffect(() => {
    fetchTenants();
  }, [fetchTenants]);

  useEffect(() => {
    const handleSessionExpired = () => {
      setAuthenticated(false);
      setTenants([]);
      setSelectedTenantId('');
    };
    window.addEventListener('np:session-expired', handleSessionExpired);
    return () => window.removeEventListener('np:session-expired', handleSessionExpired);
  }, []);

  const setAuthenticatedRole = () => {
    const authenticatedRole = roleForClaims();
    setRole(authenticatedRole);
    navigate(rolePaths[authenticatedRole], { replace: true });
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

  const roleNavItems = [
    { id: 'superadmin' as Role, label: 'Super Admin', icon: ShieldCheck, desc: 'Platform Management' },
    { id: 'vendor' as Role, label: 'ISP / Vendor', icon: Building2, desc: 'WISP Operations Suite' },
    { id: 'enduser' as Role, label: 'Customer Portal', icon: Smartphone, desc: 'Subscriber Self-Service' },
  ].filter((item) => item.id === role);

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-zinc-950">
        <div className="flex flex-col items-center gap-3">
          <div className="h-10 w-10 animate-spin rounded-full border-2 border-white/20 border-t-cyan-400" />
          <p className="text-sm text-zinc-400">Syncing your workspace...</p>
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
          <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-gradient-to-br from-cyan-400 to-indigo-600 shadow-lg shadow-cyan-500/20">
            <Radio className="h-5 w-5 text-[#071014]" />
          </div>
          <div>
            <h1 className="text-base font-bold text-white leading-tight">NetPulse Core</h1>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-cyan-400">Cloud Operations</p>
          </div>
        </div>

        {/* 3 Distinct Role-Based Operational Workflows */}
        <div className="border-b border-white/10 px-4 py-4">
          <p className="mb-2 px-2 text-[10px] font-bold uppercase tracking-[0.18em] text-zinc-500">Operational Workflows</p>
          <div className="space-y-1">
            {roleNavItems.map((item) => {
              const isActive = role === item.id;
              const Icon = item.icon;
              return (
                <button
                  key={item.id}
                  onClick={() => {
                    setRole(item.id);
                    navigate(rolePaths[item.id]);
                    setSidebarOpen(false);
                  }}
                  className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 transition ${
                    isActive ? 'bg-cyan-400/15 text-cyan-300 border border-cyan-400/30' : 'text-zinc-400 hover:bg-white/5 hover:text-white'
                  }`}
                >
                  <Icon className={`h-4 w-4 ${isActive ? 'text-cyan-400' : 'text-zinc-500'}`} />
                  <div className="text-left">
                    <p className="text-xs font-bold leading-tight">{item.label}</p>
                    <p className="text-[10px] text-zinc-500">{item.desc}</p>
                  </div>
                  {isActive && <div className="ml-auto h-2 w-2 rounded-full bg-cyan-400 shadow-sm shadow-cyan-400" />}
                </button>
              );
            })}
          </div>
        </div>

        {/* Vendor Selector (for Vendor & Customer Portal) */}
        {(role === 'vendor' || role === 'enduser') && (
          <div className="border-b border-white/10 px-4 py-4">
            <p className="mb-2 px-2 text-[10px] font-bold uppercase tracking-wider text-zinc-500">Active Tenant (WISP)</p>
            <div className="relative">
              <select
                value={selectedTenantId}
                onChange={(e) => setSelectedTenantId(e.target.value)}
                className="w-full appearance-none rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 pr-8 text-xs text-white focus:border-cyan-400 focus:outline-none"
              >
                {tenants.map((t) => (
                  <option key={t.id} value={t.id} className="bg-zinc-900">
                    {t.business_name}
                  </option>
                ))}
              </select>
              <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500" />
            </div>
          </div>
        )}

        {/* Status Footer */}
        <div className="mt-auto border-t border-white/10 px-4 py-4">
          <div className="flex items-center gap-2 rounded-xl border border-emerald-500/20 bg-emerald-500/5 px-3 py-2.5">
            <div className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
            <span className="text-xs font-medium text-emerald-300">Phase 8 Ready · RADIUS Online</span>
          </div>
          <p className="mt-2 px-2 text-[10px] text-zinc-500">NetPulse v1.8 · Multi-tenant ISP Core</p>
        </div>
      </aside>

      {/* Mobile overlay */}
      {sidebarOpen && (
        <div className="fixed inset-0 z-30 bg-black/60 backdrop-blur-sm lg:hidden" onClick={() => setSidebarOpen(false)} />
      )}

      {/* Main Content Area */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Top Header Bar */}
        <header className="flex items-center justify-between border-b border-white/10 px-6 py-3.5 bg-zinc-950/80 backdrop-blur-md">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="rounded-lg border border-white/10 p-2 text-zinc-400 hover:bg-white/5 lg:hidden"
            >
              <Menu className="h-4 w-4" />
            </button>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold text-white">
                  {role === 'superadmin' && 'Platform Governance Command Center'}
                  {role === 'vendor' && `${selectedTenant ? selectedTenant.business_name : 'WISP'} Operations`}
                  {role === 'enduser' && 'Subscriber Self-Service Portal'}
                </h2>
                <span className="hidden rounded-full border border-cyan-400/20 bg-cyan-400/10 px-2 py-0.5 text-[10px] font-bold text-cyan-200 sm:inline-flex">
                  Phase 8 Active
                </span>
              </div>
              <p className="text-xs text-zinc-400">
                {role === 'superadmin' && 'Global platform metrics, multi-tenant governance & audit logs'}
                {role === 'vendor' && (selectedTenant ? `Managing network nodes & subscribers for ${selectedTenant.business_name}` : '')}
                {role === 'enduser' && 'Active Wi-Fi package, speeds, usage tracking & Paystack M-Pesa checkouts'}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="hidden sm:flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-zinc-300 font-medium">
              <Globe className="h-3.5 w-3.5 text-cyan-400" />
              <span>/api/v1/ Connected</span>
            </div>

            <button
              onClick={handleSignOut}
              title="Sign out"
              aria-label="Sign out"
              className="flex items-center gap-1.5 rounded-xl border border-rose-400/20 px-3 py-1.5 text-xs font-semibold text-rose-300 hover:bg-rose-400/10 transition"
            >
              <LogOut className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Sign Out</span>
            </button>

            <div className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.06] px-2.5 py-1.5">
              <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-cyan-400 to-indigo-600 text-xs font-bold text-[#071014]">
                {role === 'superadmin' ? 'SA' : role === 'vendor' ? 'V' : 'U'}
              </div>
              <span className="hidden text-xs font-bold text-white capitalize sm:inline">
                {role === 'superadmin' ? 'Super Admin' : role === 'vendor' ? 'WISP Vendor' : 'Subscriber'}
              </span>
            </div>
          </div>
        </header>

        {/* Workflow Screen Router */}
        <main className="app-main flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8">
          <Routes>
            <Route path={rolePaths.superadmin} element={<SuperAdminDashboard />} />
            <Route
              path={rolePaths.vendor}
              element={selectedTenant
                ? <VendorDashboard tenant={selectedTenant} onBrandingChange={fetchTenants} />
                : <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-6 text-sm text-zinc-400">No tenant workspace is available for this account.</div>}
            />
            <Route
              path={rolePaths.enduser}
              element={selectedTenant
                ? <CustomerPortal tenant={selectedTenant} />
                : <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-6 text-sm text-zinc-400">Select a tenant to preview its subscriber portal.</div>}
            />
            <Route path="*" element={<Navigate to={rolePaths[role]} replace />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <AppContent />
      </ToastProvider>
    </BrowserRouter>
  );
}
