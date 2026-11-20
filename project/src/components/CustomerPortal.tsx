import { useState, useEffect, useCallback } from 'react';
import { api, type TransactionStatusResponse } from '@/lib/api';
import { submitHotspotLogin } from '@/lib/hotspot';
import { useToast } from '@/components/Toast';
import Modal from '@/components/Modal';
import StatusBadge from '@/components/StatusBadge';
import {
  formatCurrency, formatDuration, formatSpeed, formatBytes,
  formatDateTime, formatDate,
} from '@/lib/utils';
import type { Tenant, HotspotPlan, Transaction, Invoice, SupportTicket, ActiveSession } from '@/lib/types';
import {
  Wifi, Smartphone, CreditCard, Ticket, CheckCircle2,
  Gauge, Signal, ShieldCheck, Download,
  Send, User, AlertCircle, Phone, Printer, Check, Radio,
} from 'lucide-react';

interface CustomerPortalProps {
  tenant: Tenant;
}

type PortalTab = 'my_plan' | 'buy_package' | 'invoices' | 'usage' | 'support';

export default function CustomerPortal({ tenant }: CustomerPortalProps) {
  const { toast } = useToast();
  const [activeTab, setActiveTab] = useState<PortalTab>('my_plan');
  const [plans, setPlans] = useState<HotspotPlan[]>([]);
  const [loading, setLoading] = useState(true);

  // Subscriber Identification
  const [subscriberPhone, setSubscriberPhone] = useState('');
  const [subscriberMac, setSubscriberMac] = useState('');
  const [subscriberIp, setSubscriberIp] = useState('');
  const [subscriberUsername, setSubscriberUsername] = useState('');

  // Active Plan & Countdown
  const [activePlan, setActivePlan] = useState<HotspotPlan | null>(null);
  const [timeRemainingSeconds, setTimeRemainingSeconds] = useState(0);
  const [sessionActive, setSessionActive] = useState(false);

  const [downloadBytes, setDownloadBytes] = useState(0);
  const [uploadBytes, setUploadBytes] = useState(0);
  const [sessionHistory, setSessionHistory] = useState<ActiveSession[]>([]);
  const [activeSession, setActiveSession] = useState<ActiveSession | null>(null);

  // Checkout Flow
  const [selectedPlanForCheckout, setSelectedPlanForCheckout] = useState<HotspotPlan | null>(null);
  const [checkoutPhone, setCheckoutPhone] = useState('');
  const [checkoutStage, setCheckoutStage] = useState<'idle' | 'prompting' | 'polling' | 'success' | 'failed'>('idle');
  const [checkoutStatusText, setCheckoutStatusText] = useState('');
  const [hotspotCredentials, setHotspotCredentials] = useState<{
    username: string;
    password: string;
  } | null>(null);
  const [voucherCodeInput, setVoucherCodeInput] = useState('');
  const [redeemingVoucher, setRedeemingVoucher] = useState(false);

  // Past Transactions & Invoices
  const [myTransactions, setMyTransactions] = useState<Transaction[]>([]);
  const [myInvoices, setMyInvoices] = useState<Invoice[]>([]);
  const [selectedInvoiceForModal, setSelectedInvoiceForModal] = useState<Invoice | null>(null);

  // Support Tickets
  const [myTickets, setMyTickets] = useState<SupportTicket[]>([]);
  const [showNewTicketModal, setShowNewTicketModal] = useState(false);
  const [ticketSubject, setTicketSubject] = useState('');
  const [ticketMessage, setTicketMessage] = useState('');
  const [ticketPriority, setTicketPriority] = useState<SupportTicket['priority']>('MEDIUM');

  // Account security
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [updatingPassword, setUpdatingPassword] = useState(false);

  // Load Plans and Data
  const loadPortalData = useCallback(async () => {
    try {
      const [fetchedPlans, fetchedTx, fetchedInvoices, fetchedTickets, profile, sessions, history] = await Promise.all([
        api.getPlans(tenant.id, true),
        api.getTransactions(tenant.id),
        api.getInvoices(tenant.id),
        api.getTickets(tenant.id),
        api.getCustomerProfile(),
        api.getActiveSessions(tenant.id),
        api.getSessionHistory(tenant.id),
      ]);
      setPlans(fetchedPlans);
      setSubscriberPhone(profile.phone_number);
      setCheckoutPhone(profile.phone_number);
      setSubscriberMac(profile.mac_address);
      setSubscriberUsername(profile.username);
      setSubscriberIp(profile.ip_address || '');
      const currentSession = sessions.find((session) =>
        session.username === profile.username || session.mac_address.toLowerCase() === profile.mac_address.toLowerCase()
      ) || null;
      const plan = fetchedPlans.find((candidate) => candidate.name === profile.plan_name) || null;
      const remaining = profile.status === 'active' && profile.expires_at
        ? Math.max(0, Math.floor((new Date(profile.expires_at).getTime() - Date.now()) / 1000))
        : 0;
      setActiveSession(currentSession);
      setSessionHistory(history);
      setActivePlan(plan);
      setTimeRemainingSeconds(remaining);
      setSessionActive(Boolean(currentSession) && remaining > 0);
      setDownloadBytes(currentSession?.rx_bytes ?? profile.download_bytes);
      setUploadBytes(currentSession?.tx_bytes ?? profile.upload_bytes);
      setMyTransactions(fetchedTx);
      setMyInvoices(fetchedInvoices);
      setMyTickets(fetchedTickets.slice(0, 3));
    } catch (error) {
      toast(error instanceof Error ? error.message : 'Unable to load subscriber account data', 'error');
    } finally {
      setLoading(false);
    }
  }, [tenant.id, toast]);

  useEffect(() => {
    loadPortalData();
  }, [loadPortalData]);

  // Countdown Interval
  useEffect(() => {
    if (timeRemainingSeconds <= 0) return;
    const interval = setInterval(() => {
      setTimeRemainingSeconds((prev) => Math.max(0, prev - 1));
    }, 1000);
    return () => clearInterval(interval);
  }, [timeRemainingSeconds]);

  const formatCountdown = (secs: number) => {
    const hours = Math.floor(secs / 3600);
    const minutes = Math.floor((secs % 3600) / 60);
    const seconds = secs % 60;
    return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
  };

  // Paystack M-Pesa checkout flow
  const handleInitiateMpesa = async () => {
    if (!selectedPlanForCheckout) return;
    const cleanPhone = checkoutPhone.trim().replace(/[\s()-]/g, '');
    if (!/^(?:\+?254[17]\d{8}|0[17]\d{8}|[17]\d{8})$/.test(cleanPhone)) {
      toast('Enter a valid Kenyan mobile number, such as 0712345678', 'error');
      return;
    }
    setCheckoutStage('prompting');
    setCheckoutStatusText('Sending a Paystack M-Pesa prompt to your phone...');
    setHotspotCredentials(null);
    try {
      const payment = await api.initiatePaystackMobileMoney({
        tenant_id: tenant.id,
        plan_id: selectedPlanForCheckout.id,
        phone_number: cleanPhone,
        mac_address: subscriberMac,
      });

      setCheckoutStage('polling');
      setCheckoutStatusText('Approve the M-Pesa prompt on your phone. Awaiting payment confirmation...');

      let status: TransactionStatusResponse | null = null;
      for (let i = 0; i < 20; i++) {
        await new Promise((r) => setTimeout(r, 2000));
        try {
          status = await api.getTransactionStatus(payment.checkout_request_id);
          if (status.status === 'COMPLETED' || status.status === 'completed') break;
          if (status.status === 'FAILED' || status.status === 'failed') break;
        } catch {
          // keep polling
        }
      }

      if (status && (status.status === 'COMPLETED' || status.status === 'completed')) {
        const credentials = status.hotspot_username && status.hotspot_password
          ? {
            username: status.hotspot_username,
            password: status.hotspot_password,
          }
          : null;
        setHotspotCredentials(credentials);
        setCheckoutStage('success');
        setCheckoutStatusText('Payment confirmed. Sign in to activate your Wi-Fi session.');
        await loadPortalData();
        toast('Paystack M-Pesa payment confirmed.');
        const hotspotParams = new URLSearchParams(window.location.search);
        const loginUrl = hotspotParams.get('link-login-only') || hotspotParams.get('link-login');
        const destination = hotspotParams.get('dst') || hotspotParams.get('link-orig') || '';
        if (credentials && loginUrl) {
          try {
            submitHotspotLogin(loginUrl, destination, credentials);
          } catch {
            setCheckoutStatusText('Payment confirmed, but automatic hotspot login could not start. Use the credentials below.');
            toast('Automatic hotspot login could not start. Use the credentials below.', 'warning');
          }
        }
      } else {
        setCheckoutStage('failed');
        setCheckoutStatusText(
          status?.status === 'FAILED' || status?.status === 'failed'
            ? 'The M-Pesa payment was not completed. You can retry or choose another package.'
            : 'Payment confirmation timed out. Check your M-Pesa messages before trying again.'
        );
        toast('Payment was not confirmed. Check the transaction status before retrying.', 'error');
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to start the Paystack M-Pesa payment.';
      setCheckoutStage('failed');
      setCheckoutStatusText(message);
      toast(message, 'error');
    }
  };

  // Voucher Redemption
  const handleRedeemVoucher = async () => {
    if (!voucherCodeInput.trim()) {
      toast('Please enter a voucher code', 'error');
      return;
    }
    setRedeemingVoucher(true);
    try {
      const res = await api.redeemVoucher(voucherCodeInput.trim(), subscriberMac);
      toast(res.message);
      await loadPortalData();
      setVoucherCodeInput('');
      setActiveTab('my_plan');
    } catch (error) {
      toast(error instanceof Error ? error.message : 'Unable to redeem voucher', 'error');
    } finally {
      setRedeemingVoucher(false);
    }
  };

  // Submit Support Ticket
  const handleSubmitTicket = async () => {
    if (!ticketSubject.trim() || !ticketMessage.trim()) {
      toast('Please enter ticket subject and message', 'error');
      return;
    }
    try {
      const created = await api.createTicket({
        tenant_id: tenant.id,
        customer_name: 'Self-Service Subscriber',
        customer_phone: subscriberPhone,
        subject: ticketSubject.trim(),
        description: ticketMessage.trim(),
        priority: ticketPriority,
      });
      setMyTickets((prev) => [created, ...prev]);
      setShowNewTicketModal(false);
      setTicketSubject('');
      setTicketMessage('');
      toast(`Ticket #${created.ticket_number} submitted to support team`);
    } catch (error) {
      toast(error instanceof Error ? error.message : 'Failed to submit ticket', 'error');
    }
  };

  const handleUpdatePassword = async () => {
    if (newPassword.length < 8) {
      toast('Password must be at least 8 characters', 'error');
      return;
    }
    setUpdatingPassword(true);
    try {
      await api.changeCustomerPassword({
        current_password: currentPassword,
        new_password: newPassword,
      });
      setCurrentPassword('');
      setNewPassword('');
      toast('Account password updated successfully');
    } catch (error) {
      toast(error instanceof Error ? error.message : 'Unable to update password', 'error');
    } finally {
      setUpdatingPassword(false);
    }
  };

  const handleDownloadInvoices = () => {
    if (myInvoices.length === 0) {
      toast('There are no invoices to download', 'error');
      return;
    }
    const escapeCsv = (value: string | number) => `"${String(value).replace(/"/g, '""')}"`;
    const rows = [
      ['Invoice', 'Plan', 'Amount', 'Date', 'Due date', 'Status', 'Payment reference'],
      ...myInvoices.map((invoice) => [
        invoice.invoice_number,
        invoice.plan_name,
        invoice.amount,
        invoice.date,
        invoice.due_date,
        invoice.status,
        invoice.payment_ref || '',
      ]),
    ];
    const blob = new Blob([rows.map((row) => row.map(escapeCsv).join(',')).join('\r\n')], {
      type: 'text/csv;charset=utf-8',
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'subscriber-invoices.csv';
    link.click();
    URL.revokeObjectURL(url);
  };

  if (loading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="h-9 w-9 animate-spin rounded-full border-2 border-white/10 border-t-cyan-400" />
          <p className="text-xs text-zinc-500 font-medium">Connecting to subscriber self-service portal...</p>
        </div>
      </div>
    );
  }

  const tabsConfig: { id: PortalTab; label: string; icon: typeof Wifi }[] = [
    { id: 'my_plan', label: 'My Plan & Status', icon: Wifi },
    { id: 'buy_package', label: 'Buy Package', icon: CreditCard },
    { id: 'invoices', label: 'Payments & Invoices', icon: Download },
    { id: 'usage', label: 'Connection & Usage', icon: Gauge },
    { id: 'support', label: 'Profile & Support', icon: User },
  ];

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      {/* Subscriber Header Bar */}
      <div className="flex flex-col gap-4 rounded-2xl border border-white/10 bg-gradient-to-r from-[#0b2024] to-[#071014] p-6 shadow-xl sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-4">
          <div
            className="flex h-12 w-12 items-center justify-center rounded-2xl shadow-lg border border-white/20 text-white font-bold"
            style={{ background: tenant.brand_color || '#06b6d4' }}
          >
            {tenant.logo_url ? (
              <img src={tenant.logo_url} alt={tenant.business_name} className="h-8 w-8 object-contain rounded-xl" />
            ) : (
              <Radio className="h-6 w-6 text-white" />
            )}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-xl font-bold text-white">{tenant.business_name}</h2>
              <span className="rounded-full bg-emerald-500/10 px-2.5 py-0.5 text-[10px] font-bold text-emerald-300 border border-emerald-500/20">
                Connected
              </span>
            </div>
            <p className="text-xs text-zinc-400">Subscriber Portal · Phone: <span className="font-mono text-cyan-300">{subscriberPhone}</span></p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-right">
            <p className="text-[10px] uppercase tracking-wider text-zinc-400 font-semibold">Active Session</p>
            <p className="font-mono text-xs font-bold text-emerald-400">
              {sessionActive && timeRemainingSeconds > 0 ? formatCountdown(timeRemainingSeconds) : 'EXPIRED'}
            </p>
          </div>
          <button
            onClick={() => setActiveTab('buy_package')}
            className="rounded-xl bg-cyan-400 px-4 py-2 text-xs font-bold text-[#071014] hover:bg-cyan-300 transition shadow-lg shadow-cyan-400/20"
          >
            Buy / Extend
          </button>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="flex gap-2 overflow-x-auto rounded-2xl border border-white/10 bg-white/[0.02] p-1.5">
        {tabsConfig.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex shrink-0 items-center gap-2 rounded-xl px-4 py-2.5 text-xs font-semibold transition ${
                isActive
                  ? 'bg-cyan-400 text-[#071014] shadow-md shadow-cyan-400/20'
                  : 'text-zinc-400 hover:bg-white/5 hover:text-white'
              }`}
            >
              <Icon className="h-4 w-4" />
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>

      {/* ========================================================================= */}
      {/* 1. DASHBOARD / MY PLAN */}
      {/* ========================================================================= */}
      {activeTab === 'my_plan' && (
        <div className="space-y-6">
          {activePlan && timeRemainingSeconds > 0 ? (
            <div className="glass-card rounded-2xl p-6 sm:p-8 relative overflow-hidden">
              <div className="absolute right-0 top-0 -mr-16 -mt-16 h-64 w-64 rounded-full bg-cyan-500/10 blur-3xl pointer-events-none" />

              <div className="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
                <div>
                  <span className="rounded-full bg-cyan-400/10 px-3 py-1 text-xs font-bold text-cyan-300 border border-cyan-400/20 uppercase tracking-wider">
                    {sessionActive ? 'Connected Subscription' : 'Assigned Subscription'}
                  </span>
                  <h3 className="mt-3 text-3xl font-extrabold text-white tracking-tight">{activePlan.name}</h3>
                  <p className="mt-1 text-xs text-zinc-400">Your currently assigned subscriber package.</p>

                  <div className="mt-6 flex flex-wrap gap-4 text-xs">
                    <div className="rounded-xl border border-white/10 bg-white/5 px-4 py-2.5">
                      <p className="text-[10px] text-zinc-500 uppercase font-semibold">Download Rate</p>
                      <p className="mt-0.5 font-bold text-cyan-300 text-sm">{formatSpeed(activePlan.download_speed_kbps)}</p>
                    </div>
                    <div className="rounded-xl border border-white/10 bg-white/5 px-4 py-2.5">
                      <p className="text-[10px] text-zinc-500 uppercase font-semibold">Upload Rate</p>
                      <p className="mt-0.5 font-bold text-indigo-300 text-sm">{formatSpeed(activePlan.upload_speed_kbps)}</p>
                    </div>
                    <div className="rounded-xl border border-white/10 bg-white/5 px-4 py-2.5">
                      <p className="text-[10px] text-zinc-500 uppercase font-semibold">Simultaneous Devices</p>
                      <p className="mt-0.5 font-bold text-white text-sm">{activePlan.simultaneous_devices} Device</p>
                    </div>
                  </div>
                </div>

                {/* Expiration Countdown Card */}
                <div className="flex flex-col items-center justify-center rounded-2xl border border-cyan-400/20 bg-cyan-400/[0.05] p-6 text-center">
                  <p className="text-xs uppercase tracking-wider text-cyan-300 font-semibold mb-2">Time Remaining</p>
                  <p className="font-mono text-4xl font-extrabold tracking-wider text-white">
                    {formatCountdown(timeRemainingSeconds)}
                  </p>
                  <p className="mt-2 text-[11px] text-zinc-400">Automatic renewal prompt when under 10m</p>

                  <div className="mt-4 flex gap-2">
                    <button
                      onClick={() => setActiveTab('buy_package')}
                      className="rounded-xl bg-cyan-400 px-4 py-2 text-xs font-bold text-[#071014] hover:bg-cyan-300 transition"
                    >
                      Top-Up Time
                    </button>
                    <button
                      onClick={loadPortalData}
                      className="rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs font-medium text-white hover:bg-white/10 transition"
                    >
                      Verify Token
                    </button>
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="glass-card rounded-2xl p-8 text-center space-y-4">
              <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-amber-500/10 text-amber-400 border border-amber-500/20">
                <AlertCircle className="h-7 w-7" />
              </div>
              <h3 className="text-xl font-bold text-white">No Active Plan</h3>
              <p className="text-xs text-zinc-400 max-w-md mx-auto">
                You do not have an active Wi-Fi lease. Select a package below with instant M-Pesa checkout or redeem a voucher to get online immediately.
              </p>
              <div className="flex justify-center gap-3 pt-2">
                <button
                  onClick={() => setActiveTab('buy_package')}
                  className="rounded-xl bg-cyan-400 px-5 py-2.5 text-xs font-bold text-[#071014] hover:bg-cyan-300 transition shadow-lg shadow-cyan-400/20"
                >
                  Buy Internet Package
                </button>
              </div>
            </div>
          )}

          {/* Quick Network Status Card */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="glass-card rounded-2xl p-4 flex items-center gap-3">
              <div className="rounded-xl bg-cyan-400/10 p-2.5 text-cyan-300 border border-cyan-400/20">
                <Signal className="h-5 w-5" />
              </div>
              <div>
                <p className="text-[10px] uppercase font-semibold text-zinc-400">Signal Strength</p>
                <p className="font-bold text-white text-sm">{sessionActive ? 'Connected' : 'Offline'}</p>
              </div>
            </div>
            <div className="glass-card rounded-2xl p-4 flex items-center gap-3">
              <div className="rounded-xl bg-indigo-500/10 p-2.5 text-indigo-400 border border-indigo-500/20">
                <Smartphone className="h-5 w-5" />
              </div>
              <div>
                <p className="text-[10px] uppercase font-semibold text-zinc-400">Assigned IP</p>
                <p className="font-mono font-bold text-white text-sm">{subscriberIp}</p>
              </div>
            </div>
            <div className="glass-card rounded-2xl p-4 flex items-center gap-3">
              <div className="rounded-xl bg-emerald-500/10 p-2.5 text-emerald-400 border border-emerald-500/20">
                <ShieldCheck className="h-5 w-5" />
              </div>
              <div>
                <p className="text-[10px] uppercase font-semibold text-zinc-400">Gateway Encryption</p>
                <p className="font-bold text-white text-sm">{activeSession ? 'RADIUS authenticated' : 'No active session'}</p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 2. BUY PACKAGE & CHECKOUT */}
      {/* ========================================================================= */}
      {activeTab === 'buy_package' && (
        <div className="space-y-6">
          <div className="border-b border-white/10 pb-4">
            <h3 className="text-xl font-bold text-white">Choose Your Internet Package</h3>
            <p className="text-xs text-zinc-400">Fast activation via Paystack M-Pesa mobile money or voucher scratch code</p>
          </div>

          {/* Plan Cards Grid */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {plans.map((plan) => (
              <div
                key={plan.id}
                className={`glass-card rounded-2xl p-5 flex flex-col justify-between transition hover:-translate-y-1 hover:border-cyan-400/40 ${
                  activePlan?.id === plan.id ? 'border-cyan-400/50 bg-cyan-400/[0.04]' : ''
                }`}
              >
                <div>
                  <div className="flex items-center justify-between">
                    <span className="rounded-lg bg-white/5 px-2.5 py-1 text-[11px] font-semibold text-zinc-300">
                      {formatDuration(plan.duration_minutes)}
                    </span>
                    <span className="font-mono text-xs font-bold text-cyan-300">
                      {formatSpeed(plan.download_speed_kbps)}
                    </span>
                  </div>
                  <h4 className="mt-3 text-lg font-bold text-white">{plan.name}</h4>
                  <p className="text-2xl font-black text-white mt-2">
                    {formatCurrency(Number(plan.price))}
                  </p>
                  <ul className="mt-4 space-y-1.5 text-xs text-zinc-400">
                    <li className="flex items-center gap-2">
                      <Check className="h-3.5 w-3.5 text-cyan-400" />
                      <span>{formatSpeed(plan.download_speed_kbps)} Download speed</span>
                    </li>
                    <li className="flex items-center gap-2">
                      <Check className="h-3.5 w-3.5 text-cyan-400" />
                      <span>{formatSpeed(plan.upload_speed_kbps)} Upload speed</span>
                    </li>
                    <li className="flex items-center gap-2">
                      <Check className="h-3.5 w-3.5 text-cyan-400" />
                      <span>{plan.simultaneous_devices} Device connection</span>
                    </li>
                  </ul>
                </div>

                <button
                  onClick={() => {
                    setSelectedPlanForCheckout(plan);
                    setCheckoutStage('idle');
                  }}
                  className="mt-6 w-full rounded-xl bg-cyan-400 py-2.5 text-xs font-bold text-[#071014] hover:bg-cyan-300 transition shadow-md shadow-cyan-400/20"
                >
                  Buy with M-Pesa
                </button>
              </div>
            ))}
          </div>

          {/* Voucher Redemption Option */}
          <div className="glass-card rounded-2xl p-6 border-dashed border-cyan-400/30">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <Ticket className="h-5 w-5 text-cyan-300" />
                  <h4 className="text-sm font-bold text-white">Have a Scratch Voucher Card?</h4>
                </div>
                <p className="text-xs text-zinc-400 mt-1">Enter your printed or scratch voucher code to activate internet access immediately.</p>
              </div>

              <div className="flex gap-2 w-full sm:w-auto">
                <input
                  type="text"
                  placeholder="Enter Voucher Code..."
                  value={voucherCodeInput}
                  onChange={(e) => setVoucherCodeInput(e.target.value.toUpperCase())}
                  className="rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs font-mono uppercase text-white outline-none focus:border-cyan-400 w-full sm:w-48"
                />
                <button
                  onClick={handleRedeemVoucher}
                  disabled={redeemingVoucher}
                  className="rounded-xl bg-white/10 px-4 py-2 text-xs font-semibold text-white hover:bg-white/20 transition shrink-0"
                >
                  {redeemingVoucher ? 'Redeeming...' : 'Activate Voucher'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 3. PAYMENT HISTORY & INVOICES */}
      {/* ========================================================================= */}
      {activeTab === 'invoices' && (
        <div className="glass-card rounded-2xl overflow-hidden">
          <div className="flex items-center justify-between border-b border-white/10 px-6 py-4">
            <div>
              <h3 className="text-base font-bold text-white">Payment History & Tax Invoices</h3>
              <p className="text-xs text-zinc-400">Download and view official receipts for past Wi-Fi and broadband packages</p>
            </div>
            <button
              onClick={handleDownloadInvoices}
              className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-1.5 text-xs font-semibold text-white hover:bg-white/10 transition"
            >
              <Download className="h-3.5 w-3.5" /> Download Receipts
            </button>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-white/10 bg-white/[0.02] text-xs font-medium text-zinc-400">
                <tr>
                  <th className="px-6 py-3.5">M-Pesa Reference</th>
                  <th className="px-6 py-3.5">Package</th>
                  <th className="px-6 py-3.5">Amount (KES)</th>
                  <th className="px-6 py-3.5">Date & Time</th>
                  <th className="px-6 py-3.5">Status</th>
                  <th className="px-6 py-3.5 text-right">Invoice</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {myTransactions.map((tx) => (
                  <tr key={tx.id} className="hover:bg-white/[0.02] transition">
                    <td className="px-6 py-4 font-mono font-bold text-cyan-300 text-xs">
                      {tx.payment_ref || String(tx.id).slice(0, 10)}
                    </td>
                    <td className="px-6 py-4 text-xs font-semibold text-white">
                      {plans.find((plan) => plan.id === tx.plan_id)?.name || 'Package'}
                    </td>
                    <td className="px-6 py-4 font-bold text-white">
                      {formatCurrency(Number(tx.gross_amount))}
                    </td>
                    <td className="px-6 py-4 text-xs text-zinc-400">
                      {formatDateTime(tx.created_at)}
                    </td>
                    <td className="px-6 py-4">
                      <StatusBadge status={tx.status} />
                    </td>
                    <td className="px-6 py-4 text-right">
                      <button
                        onClick={() => {
                          setSelectedInvoiceForModal({
                            id: tx.id,
                            tenant_id: tenant.id,
                            invoice_number: `INV-${tx.payment_ref || '2026-99'}`,
                            customer_name: 'Subscriber (' + subscriberPhone + ')',
                            customer_phone: subscriberPhone,
                            plan_name: plans.find((plan) => plan.id === tx.plan_id)?.name || 'Wi-Fi Package',
                            amount: Number(tx.gross_amount),
                            date: tx.created_at.slice(0, 10),
                            due_date: tx.created_at.slice(0, 10),
                            status: tx.status === 'COMPLETED' || tx.status === 'completed' ? 'PAID' : 'UNPAID',
                            payment_ref: tx.payment_ref,
                          });
                        }}
                        className="rounded-lg border border-white/10 px-2.5 py-1 text-xs text-zinc-300 hover:bg-white/10 transition"
                      >
                        View Receipt
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="border-t border-white/10 px-6 py-4">
            <h4 className="text-sm font-bold text-white">Invoices</h4>
            <p className="mt-1 text-xs text-zinc-400">Invoices issued to your subscriber account.</p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-white/10 bg-white/[0.02] text-xs font-medium text-zinc-400">
                <tr>
                  <th className="px-6 py-3.5">Invoice</th>
                  <th className="px-6 py-3.5">Package</th>
                  <th className="px-6 py-3.5">Amount</th>
                  <th className="px-6 py-3.5">Date</th>
                  <th className="px-6 py-3.5">Status</th>
                  <th className="px-6 py-3.5 text-right">Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {myInvoices.map((invoice) => (
                  <tr key={invoice.id} className="hover:bg-white/[0.02]">
                    <td className="px-6 py-4 font-mono text-xs text-cyan-300">{invoice.invoice_number}</td>
                    <td className="px-6 py-4 text-xs text-white">{invoice.plan_name}</td>
                    <td className="px-6 py-4 font-bold text-white">{formatCurrency(Number(invoice.amount))}</td>
                    <td className="px-6 py-4 text-xs text-zinc-400">{formatDate(invoice.date)}</td>
                    <td className="px-6 py-4"><StatusBadge status={invoice.status} /></td>
                    <td className="px-6 py-4 text-right">
                      <button
                        onClick={() => setSelectedInvoiceForModal(invoice)}
                        className="rounded-lg border border-white/10 px-2.5 py-1 text-xs text-zinc-300 hover:bg-white/10"
                      >
                        View Invoice
                      </button>
                    </td>
                  </tr>
                ))}
                {myInvoices.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-6 py-8 text-center text-zinc-500">No invoices are available.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 4. CONNECTION STATUS & USAGE */}
      {/* ========================================================================= */}
      {activeTab === 'usage' && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div className="glass-card rounded-2xl p-5">
              <p className="text-[10px] uppercase font-bold text-zinc-400">Total Downloaded</p>
              <p className="mt-2 text-2xl font-bold text-cyan-300">{formatBytes(downloadBytes)}</p>
              <p className="text-xs text-zinc-500 mt-1">This billing cycle</p>
            </div>
            <div className="glass-card rounded-2xl p-5">
              <p className="text-[10px] uppercase font-bold text-zinc-400">Total Uploaded</p>
              <p className="mt-2 text-2xl font-bold text-indigo-300">{formatBytes(uploadBytes)}</p>
              <p className="text-xs text-zinc-500 mt-1">Upstream traffic</p>
            </div>
            <div className="glass-card rounded-2xl p-5">
              <p className="text-[10px] uppercase font-bold text-zinc-400">Device Hardware MAC</p>
              <p className="mt-2 font-mono text-sm font-bold text-white">{subscriberMac}</p>
              <p className="text-xs text-zinc-500 mt-1">Registered device</p>
            </div>
            <div className="glass-card rounded-2xl p-5">
              <p className="text-[10px] uppercase font-bold text-zinc-400">Connection Lease</p>
              <p className={`mt-2 text-2xl font-bold ${sessionActive ? 'text-emerald-400' : 'text-zinc-500'}`}>
                {sessionActive ? 'Active' : 'Inactive'}
              </p>
              <p className="text-xs text-zinc-500 mt-1">{activeSession?.router_name || 'No active router session'}</p>
            </div>
          </div>

          {/* Session History Log */}
          <div className="glass-card rounded-2xl overflow-hidden">
            <div className="border-b border-white/10 px-6 py-4">
              <h4 className="font-bold text-white text-sm">Recent Connection Sessions</h4>
              <p className="text-xs text-zinc-400">Historical connections logged by venue NAS controller</p>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-white/10 bg-white/[0.02] text-xs font-medium text-zinc-400">
                  <tr>
                    <th className="px-6 py-3.5">Started At</th>
                    <th className="px-6 py-3.5">Duration</th>
                    <th className="px-6 py-3.5">Downloaded</th>
                    <th className="px-6 py-3.5">Uploaded</th>
                    <th className="px-6 py-3.5">Disconnect Cause</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5 text-xs">
                  {[...(activeSession ? [activeSession] : []), ...sessionHistory].map((session) => (
                    <tr key={session.id} className="hover:bg-white/[0.02]">
                      <td className="px-6 py-3.5 text-zinc-300">{formatDateTime(session.started_at)}</td>
                      <td className="px-6 py-3.5 text-white font-medium">
                        {session.stopped_at
                          ? formatDuration(Math.floor(session.uptime_seconds / 60))
                          : 'Active (Current)'}
                      </td>
                      <td className="px-6 py-3.5 text-cyan-300 font-mono">{formatBytes(session.rx_bytes)}</td>
                      <td className="px-6 py-3.5 text-zinc-400 font-mono">{formatBytes(session.tx_bytes)}</td>
                      <td className="px-6 py-3.5 text-zinc-500">
                        {session.terminate_cause || (session.stopped_at ? 'Disconnected' : 'Online')}
                      </td>
                    </tr>
                  ))}
                  {sessionHistory.length === 0 && !activeSession && (
                    <tr>
                      <td colSpan={5} className="px-6 py-8 text-center text-zinc-500">
                        No connection sessions have been recorded.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 5. PROFILE & SUPPORT */}
      {/* ========================================================================= */}
      {activeTab === 'support' && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
            {/* Account Details & PIN */}
            <div className="glass-card rounded-2xl p-6 space-y-4">
              <h4 className="font-bold text-white text-base">Subscriber Account Details</h4>
              <div className="space-y-3 text-xs">
                <div>
                  <label className="text-zinc-500">Mobile Phone</label>
                  <p className="font-mono text-sm font-semibold text-white mt-0.5">{subscriberPhone}</p>
                </div>
                <div>
                  <label className="text-zinc-500">Subscriber Username</label>
                  <p className="font-mono text-sm font-semibold text-white mt-0.5">{subscriberUsername}</p>
                </div>
                <div>
                  <label className="text-zinc-500">Device Hardware MAC Address</label>
                  <p className="font-mono text-sm font-semibold text-cyan-300 mt-0.5">{subscriberMac}</p>
                </div>
                <div>
                  <label className="text-zinc-500">Venue Network</label>
                  <p className="text-sm font-semibold text-white mt-0.5">{tenant.business_name}</p>
                </div>
              </div>

              <div className="pt-4 border-t border-white/10">
                <h5 className="font-bold text-white text-xs uppercase tracking-wider mb-2">Change Account Password</h5>
                <div className="space-y-2">
                  <input
                    type="password"
                    autoComplete="current-password"
                    placeholder="Current password"
                    value={currentPassword}
                    onChange={(e) => setCurrentPassword(e.target.value)}
                    className="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs text-white outline-none focus:border-cyan-400"
                  />
                  <input
                    type="password"
                    autoComplete="new-password"
                    minLength={8}
                    placeholder="New password (at least 8 characters)"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    className="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs text-white outline-none focus:border-cyan-400"
                  />
                  <button
                    onClick={handleUpdatePassword}
                    disabled={updatingPassword || !currentPassword || !newPassword}
                    className="rounded-xl bg-cyan-400 px-4 py-2 text-xs font-semibold text-[#071014] hover:bg-cyan-300 transition disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {updatingPassword ? 'Updating...' : 'Update Password'}
                  </button>
                </div>
              </div>
            </div>

            {/* Direct Support & Hotline */}
            <div className="glass-card rounded-2xl p-6 space-y-4">
              <h4 className="font-bold text-white text-base">Need Help or Having Issues?</h4>
              <p className="text-xs text-zinc-400">
                Our network operations center is available 24/7 to help with speed issues, disconnections, or billing inquiries.
              </p>

              <div className="space-y-2 pt-2">
                <button
                  onClick={() => setShowNewTicketModal(true)}
                  className="w-full flex items-center justify-center gap-2 rounded-xl bg-cyan-400 py-2.5 text-xs font-semibold text-[#071014] hover:bg-cyan-300 transition"
                >
                  <Send className="h-4 w-4" /> Open Support Ticket
                </button>
                <a
                  href={`tel:${tenant.phone_number || '254700000000'}`}
                  className="w-full flex items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/5 py-2.5 text-xs font-semibold text-white hover:bg-white/10 transition"
                >
                  <Phone className="h-4 w-4" /> Call Network Hotline
                </a>
              </div>
            </div>
          </div>

          {/* Previous Tickets List */}
          <div className="glass-card rounded-2xl overflow-hidden">
            <div className="border-b border-white/10 px-6 py-4">
              <h4 className="font-bold text-white text-sm">My Previous Support Inquiries</h4>
            </div>
            <div className="divide-y divide-white/5">
              {myTickets.map((t) => (
                <div key={t.id} className="p-4 flex items-center justify-between text-xs">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono font-bold text-cyan-300">{t.ticket_number}</span>
                      <span className="font-semibold text-white">{t.subject}</span>
                    </div>
                    <p className="text-zinc-500 mt-1">{t.description}</p>
                  </div>
                  <StatusBadge status={t.status} />
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* MODALS */}
      {/* ========================================================================= */}

      {/* M-Pesa Checkout Modal */}
      <Modal
        open={Boolean(selectedPlanForCheckout)}
        onClose={() => {
          setSelectedPlanForCheckout(null);
          setCheckoutStage('idle');
        }}
        title={`Checkout: ${selectedPlanForCheckout?.name}`}
        description="Instant M-Pesa mobile-money payment securely processed by Paystack"
        size="sm"
      >
        {selectedPlanForCheckout && (
          <div className="space-y-4">
            <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4 text-xs space-y-1.5">
              <div className="flex justify-between">
                <span className="text-zinc-400">Plan Duration</span>
                <span className="font-semibold text-white">{formatDuration(selectedPlanForCheckout.duration_minutes)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-zinc-400">Bandwidth Speed</span>
                <span className="font-semibold text-cyan-300">{formatSpeed(selectedPlanForCheckout.download_speed_kbps)}</span>
              </div>
              <div className="flex justify-between border-t border-white/10 pt-2 text-sm">
                <span className="font-bold text-white">Total Amount</span>
                <span className="font-extrabold text-cyan-300">{formatCurrency(Number(selectedPlanForCheckout.price))}</span>
              </div>
            </div>

            {checkoutStage === 'idle' && (
              <div className="space-y-3">
                <div>
                  <label className="text-xs text-zinc-400 font-semibold">Enter M-Pesa Mobile Number</label>
                  <input
                    type="tel"
                    placeholder="e.g. 0712345678 or 254712345678"
                    value={checkoutPhone}
                    onChange={(e) => setCheckoutPhone(e.target.value)}
                    className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm font-mono text-white outline-none focus:border-cyan-400"
                  />
                  <p className="mt-1 text-[11px] text-zinc-500">You will receive an STK prompt on this phone to enter your PIN.</p>
                </div>
                <button
                  onClick={handleInitiateMpesa}
                  className="w-full rounded-xl bg-cyan-400 py-3 text-xs font-bold text-[#071014] hover:bg-cyan-300 transition shadow-lg shadow-cyan-400/20"
                >
                  Pay {formatCurrency(Number(selectedPlanForCheckout.price))} via M-Pesa
                </button>
              </div>
            )}

            {(checkoutStage === 'prompting' || checkoutStage === 'polling') && (
              <div className="py-6 text-center space-y-3">
                <div className="mx-auto h-10 w-10 animate-spin rounded-full border-2 border-white/20 border-t-cyan-400" />
                <p className="text-sm font-semibold text-white">Prompt Sent to Your Phone</p>
                <p className="text-xs text-zinc-400 max-w-xs mx-auto">{checkoutStatusText}</p>
              </div>
            )}

            {checkoutStage === 'success' && (
              <div className="py-6 text-center space-y-3">
                <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                  <CheckCircle2 className="h-6 w-6" />
                </div>
                <p className="text-base font-bold text-white">Payment Confirmed</p>
                <p className="text-xs text-zinc-400">{checkoutStatusText}</p>
                {hotspotCredentials && (
                  <div className="rounded-xl border border-white/10 bg-black/30 p-3 text-left">
                    <p className="text-[10px] text-zinc-500">Hotspot Login</p>
                    <p className="mt-1 font-mono text-xs text-zinc-300">Username: {hotspotCredentials.username}</p>
                    <p className="mt-1 font-mono text-xs text-zinc-300">Password: {hotspotCredentials.password}</p>
                  </div>
                )}
                <button
                  onClick={() => {
                    setSelectedPlanForCheckout(null);
                    setCheckoutStage('idle');
                    setHotspotCredentials(null);
                    setActiveTab('my_plan');
                  }}
                  className="mt-2 rounded-xl bg-cyan-400 px-6 py-2 text-xs font-bold text-[#071014] hover:bg-cyan-300 transition"
                >
                  Go to My Dashboard
                </button>
              </div>
            )}

            {checkoutStage === 'failed' && (
              <div className="py-6 text-center space-y-3">
                <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-rose-500/10 text-rose-300 border border-rose-500/20">
                  <AlertCircle className="h-6 w-6" />
                </div>
                <p className="text-base font-bold text-white">Payment Not Confirmed</p>
                <p className="text-xs text-zinc-400">{checkoutStatusText}</p>
                <button
                  onClick={() => setCheckoutStage('idle')}
                  className="mt-2 rounded-xl bg-cyan-400 px-6 py-2 text-xs font-bold text-[#071014] hover:bg-cyan-300 transition"
                >
                  Try Again
                </button>
              </div>
            )}
          </div>
        )}
      </Modal>

      {/* View Printable Invoice / Receipt Modal */}
      <Modal
        open={Boolean(selectedInvoiceForModal)}
        onClose={() => setSelectedInvoiceForModal(null)}
        title="Payment Tax Receipt"
        size="md"
      >
        {selectedInvoiceForModal && (
          <div className="space-y-6">
            <div className="rounded-xl border border-white/10 bg-white/[0.02] p-6 text-xs space-y-4">
              <div className="flex justify-between items-start border-b border-white/10 pb-4">
                <div>
                  <h4 className="text-base font-bold text-white">{tenant.business_name}</h4>
                  <p className="text-zinc-500 text-[11px]">Wi-Fi Network Operations</p>
                </div>
                <div className="text-right">
                  <span className="font-mono font-bold text-cyan-300 text-sm">{selectedInvoiceForModal.invoice_number}</span>
                  <p className="text-zinc-500 text-[11px] mt-0.5">Date: {selectedInvoiceForModal.date}</p>
                </div>
              </div>

              <div className="space-y-1">
                <p className="text-zinc-500">Billed To:</p>
                <p className="font-semibold text-white">{selectedInvoiceForModal.customer_name}</p>
                <p className="text-zinc-400 font-mono">{selectedInvoiceForModal.customer_phone}</p>
              </div>

              <div className="border-t border-b border-white/10 py-3 space-y-2">
                <div className="flex justify-between font-semibold text-white">
                  <span>{selectedInvoiceForModal.plan_name}</span>
                  <span>{formatCurrency(Number(selectedInvoiceForModal.amount))}</span>
                </div>
                <div className="flex justify-between text-zinc-400 text-[11px]">
                  <span>Payment reference</span>
                  <span className="font-mono">{selectedInvoiceForModal.payment_ref || 'Not recorded'}</span>
                </div>
              </div>

              <div className="flex justify-between text-sm font-bold text-white pt-1">
                <span>{selectedInvoiceForModal.status === 'PAID' ? 'Total Amount Paid' : 'Invoice Amount'}</span>
                <span className="text-emerald-400 font-extrabold">{formatCurrency(Number(selectedInvoiceForModal.amount))}</span>
              </div>
            </div>

            <div className="flex gap-2">
              <button
                onClick={() => {
                  window.print();
                }}
                className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-cyan-400 py-2.5 text-xs font-semibold text-[#071014] hover:bg-cyan-300 transition"
              >
                <Printer className="h-4 w-4" /> Print Receipt
              </button>
              <button
                onClick={() => setSelectedInvoiceForModal(null)}
                className="rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-xs font-semibold text-white hover:bg-white/10 transition"
              >
                Close
              </button>
            </div>
          </div>
        )}
      </Modal>

      {/* Open Support Ticket Modal */}
      <Modal
        open={showNewTicketModal}
        onClose={() => setShowNewTicketModal(false)}
        title="Submit Support Inquiry"
        description="Our network technicians will attend to your request immediately."
        size="md"
      >
        <div className="space-y-4">
          <div>
            <label className="text-xs text-zinc-400">Issue Category / Subject</label>
            <input
              type="text"
              placeholder="e.g. Cannot connect after restarting phone"
              value={ticketSubject}
              onChange={(e) => setTicketSubject(e.target.value)}
              className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
            />
          </div>
          <div>
            <label className="text-xs text-zinc-400">Priority Level</label>
            <select
              value={ticketPriority}
              onChange={(e) => setTicketPriority(e.target.value as SupportTicket['priority'])}
              className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
            >
              <option value="LOW" className="bg-zinc-900">Low - General Question</option>
              <option value="MEDIUM" className="bg-zinc-900">Medium - Degraded Speed</option>
              <option value="HIGH" className="bg-zinc-900">High - Cannot Access Internet</option>
              <option value="URGENT" className="bg-zinc-900">Urgent - Business Disruption</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-zinc-400">Detailed Message</label>
            <textarea
              rows={4}
              placeholder="Describe what happened, error message, or room number..."
              value={ticketMessage}
              onChange={(e) => setTicketMessage(e.target.value)}
              className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 p-3 text-xs text-white outline-none focus:border-cyan-400 font-sans"
            />
          </div>
          <button
            onClick={handleSubmitTicket}
            className="w-full rounded-xl bg-cyan-400 py-2.5 text-xs font-semibold text-[#071014] hover:bg-cyan-300 transition"
          >
            Submit Inquiry to Support
          </button>
        </div>
      </Modal>
    </div>
  );
}
