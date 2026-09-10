import { useState, useEffect, useCallback } from 'react';
import { api } from '@/lib/api';
import { useToast } from '@/components/Toast';
import {
  formatCurrency, formatDuration, formatSpeed,
  generateSessionToken,
} from '@/lib/utils';
import type { Tenant, HotspotPlan } from '@/lib/types';
import {
  Wifi, Smartphone, CreditCard, Ticket, CheckCircle2, Loader2,
  Clock, Gauge, ArrowLeft, Signal, Battery, Wifi as WifiIcon,
} from 'lucide-react';

interface CaptivePortalProps {
  tenant: Tenant;
}

type PortalStage = 'packages' | 'checkout' | 'processing' | 'active';

export default function CaptivePortal({ tenant }: CaptivePortalProps) {
  const { toast } = useToast();
  const [plans, setPlans] = useState<HotspotPlan[]>([]);
  const [stage, setStage] = useState<PortalStage>('packages');
  const [selectedPlan, setSelectedPlan] = useState<HotspotPlan | null>(null);
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState(false);
  const [sessionToken, setSessionToken] = useState('');
  const [timeRemaining, setTimeRemaining] = useState(0);
  const [customerPhone, setCustomerPhone] = useState('');
  const [customerMac] = useState('A4:B1:C2:D3:E4:F5');
  const [paymentMethod, setPaymentMethod] = useState<'mobile_money' | 'card' | 'voucher'>('mobile_money');
  const [voucherCode, setVoucherCode] = useState('');

  const fetchPlans = useCallback(async () => {
    try { setPlans(await api.getPlans(tenant.id, true)); }
    catch { toast('Unable to load Wi-Fi packages', 'error'); }
    finally { setLoading(false); }
  }, [tenant.id, toast]);

  useEffect(() => { fetchPlans(); }, [fetchPlans]);

  useEffect(() => {
    if (stage !== 'active' || timeRemaining <= 0) return;
    const interval = setInterval(() => {
      setTimeRemaining((prev) => Math.max(0, prev - 1));
    }, 1000);
    return () => clearInterval(interval);
  }, [stage, timeRemaining]);

  const handleSelectPlan = (plan: HotspotPlan) => {
    setSelectedPlan(plan);
    setStage('checkout');
  };

  const handlePayment = async () => {
    if (paymentMethod !== 'mobile_money') { toast('M-Pesa is the only connected payment method currently', 'warning'); return; }
    if (!/^2547\d{8}$/.test(customerPhone)) { toast('Enter a valid phone number in the format 2547XXXXXXXX', 'error'); return; }
    if (!selectedPlan) return;
    setProcessing(true);
    setStage('processing');
    try {
      const routers = await api.getRouters(tenant.id);
      const router = routers.find((item) => item.is_online) || routers[0];
      if (!router) throw new Error('No router is configured for this venue');
      const payment = await api.initiateMpesaStkPush({ nas_id: router.id, plan_id: selectedPlan.id, phone_number: customerPhone, mac_address: customerMac });
      let status = await api.getTransactionStatus(payment.checkout_request_id);
      for (let attempt = 0; attempt < 30 && status.status === 'PENDING'; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 2000));
        status = await api.getTransactionStatus(payment.checkout_request_id);
      }
      if (status.status !== 'COMPLETED') throw new Error(status.status === 'FAILED' ? 'M-Pesa payment failed or was cancelled' : 'Payment confirmation timed out');
      setSessionToken(generateSessionToken());
      setTimeRemaining(selectedPlan.duration_minutes * 60);
      setProcessing(false); setStage('active');
      toast('Payment confirmed. Connecting you to Wi-Fi.');
      window.location.href = `http://${router.nasname}/login?username=${encodeURIComponent(customerMac)}&password=${encodeURIComponent(customerMac)}`;
    } catch (error) {
      setProcessing(false); setStage('checkout');
      toast(error instanceof Error ? error.message : 'Payment could not be completed', 'error');
    }
  };

  const resetPortal = () => {
    setStage('packages');
    setSelectedPlan(null);
    setCustomerPhone('');
    setVoucherCode('');
    setSessionToken('');
    setTimeRemaining(0);
  };

  const formatTime = (s: number) => {
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = s % 60;
    return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
  };

  const brandColor = tenant.brand_color || '#6366f1';

  return (
    <div className="flex flex-col items-center justify-center gap-6 py-8">
      <div className="text-center">
        <h2 className="text-xl font-bold text-white">End-User Captive Portal Preview</h2>
        <p className="mt-1 text-sm text-zinc-500">Live preview of what customers see when connecting to {tenant.business_name} Wi-Fi</p>
      </div>

      {/* Phone Frame */}
      <div className="relative">
        {/* Phone bezel */}
        <div className="relative rounded-[2.5rem] border-[3px] border-zinc-800 bg-zinc-950 p-2 shadow-2xl">
          {/* Notch */}
          <div className="absolute left-1/2 top-2 z-20 h-6 w-32 -translate-x-1/2 rounded-b-2xl bg-zinc-800" />

          {/* Screen */}
          <div className="relative h-[600px] w-[320px] overflow-hidden rounded-[2rem] bg-gradient-to-b from-zinc-900 to-black">
            {/* Status bar */}
            <div className="flex items-center justify-between px-6 pt-3 pb-2 text-xs text-white/80">
              <span className="font-semibold">9:41</span>
              <div className="flex items-center gap-1.5">
                <Signal className="h-3.5 w-3.5" />
                <WifiIcon className="h-3.5 w-3.5" />
                <Battery className="h-4 w-4" />
              </div>
            </div>

            {/* Content */}
            <div className="h-[calc(100%-2rem)] overflow-y-auto px-5 pb-5" style={{ scrollbarWidth: 'none' }}>
              {/* Header */}
              <div className="flex flex-col items-center pt-4 pb-6">
                {tenant.logo_url ? (
                  <img src={tenant.logo_url} alt="Logo" className="h-16 w-16 rounded-2xl object-cover" />
                ) : (
                  <div className="flex h-16 w-16 items-center justify-center rounded-2xl text-2xl font-bold text-white" style={{ background: brandColor }}>
                    {tenant.business_name.charAt(0)}
                  </div>
                )}
                <h3 className="mt-3 text-center text-base font-bold text-white leading-tight">
                  {tenant.welcome_headline || 'Welcome to our Wi-Fi'}
                </h3>
                <p className="mt-1 text-xs text-zinc-500">{tenant.business_name}</p>
              </div>

              {/* Loading */}
              {loading && (
                <div className="flex h-40 items-center justify-center">
                  <Loader2 className="h-6 w-6 animate-spin text-zinc-600" />
                </div>
              )}

              {/* Stage: Packages */}
              {!loading && stage === 'packages' && (
                <div className="space-y-3 animate-[fadeIn_0.3s_ease-out]">
                  <p className="text-center text-xs font-medium text-zinc-400 mb-3">Select a Wi-Fi package to get started</p>
                  {plans.map((plan) => (
                    <button
                      key={plan.id}
                      onClick={() => handleSelectPlan(plan)}
                      className="w-full rounded-2xl border border-white/10 bg-white/[0.03] p-4 text-left transition-all hover:border-white/20 hover:bg-white/[0.06]"
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex items-center gap-3">
                          <div className="rounded-xl p-2" style={{ background: `${brandColor}20` }}>
                            <Wifi className="h-4 w-4" style={{ color: brandColor }} />
                          </div>
                          <div>
                            <p className="text-sm font-semibold text-white">{plan.name}</p>
                            <div className="mt-1 flex items-center gap-2 text-[10px] text-zinc-500">
                              <span className="flex items-center gap-0.5"><Clock className="h-3 w-3" />{formatDuration(plan.duration_minutes)}</span>
                              <span className="flex items-center gap-0.5"><Gauge className="h-3 w-3" />{formatSpeed(plan.download_speed_kbps)}</span>
                            </div>
                          </div>
                        </div>
                        <span className="text-lg font-bold text-white">{formatCurrency(plan.price)}</span>
                      </div>
                    </button>
                  ))}
                </div>
              )}

              {/* Stage: Checkout */}
              {stage === 'checkout' && selectedPlan && (
                <div className="space-y-4 animate-[fadeIn_0.3s_ease-out]">
                  <button onClick={() => setStage('packages')} className="flex items-center gap-1 text-xs text-zinc-500 hover:text-zinc-300 transition-colors">
                    <ArrowLeft className="h-3.5 w-3.5" /> Back to packages
                  </button>

                  <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-semibold text-white">{selectedPlan.name}</p>
                        <p className="text-xs text-zinc-500">{formatDuration(selectedPlan.duration_minutes)} · {formatSpeed(selectedPlan.download_speed_kbps)}</p>
                      </div>
                      <span className="text-xl font-bold text-white">{formatCurrency(selectedPlan.price)}</span>
                    </div>
                  </div>

                  <div>
                    <label className="mb-1.5 block text-xs font-medium text-zinc-400">Phone Number / Device MAC</label>
                    <input
                      value={customerPhone}
                      onChange={(e) => setCustomerPhone(e.target.value)}
                      placeholder="+254 712 345 678"
                      className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white placeholder-zinc-600 focus:border-indigo-500/50 focus:outline-none focus:ring-1 focus:ring-indigo-500/30"
                    />
                    <p className="mt-1 text-[10px] text-zinc-600 font-mono">MAC: {customerMac}</p>
                  </div>

                  <div>
                    <label className="mb-2 block text-xs font-medium text-zinc-400">Payment Method</label>
                    <div className="space-y-2">
                      {[
                        { id: 'mobile_money' as const, label: 'Mobile Money (STK Push)', icon: Smartphone },
                        { id: 'card' as const, label: 'Credit / Debit Card', icon: CreditCard },
                        { id: 'voucher' as const, label: 'Voucher Code', icon: Ticket },
                      ].map((m) => (
                        <button
                          key={m.id}
                          onClick={() => setPaymentMethod(m.id)}
                          className={`flex w-full items-center gap-3 rounded-xl border px-4 py-3 text-sm transition-colors ${
                            paymentMethod === m.id ? 'border-white/20 bg-white/10 text-white' : 'border-white/10 bg-white/[0.02] text-zinc-400'
                          }`}
                        >
                          <m.icon className="h-4 w-4" />
                          {m.label}
                          <div className={`ml-auto h-4 w-4 rounded-full border-2 ${paymentMethod === m.id ? 'border-white bg-white' : 'border-zinc-600'}`} />
                        </button>
                      ))}
                    </div>
                  </div>

                  {paymentMethod === 'voucher' && (
                    <div>
                      <label className="mb-1.5 block text-xs font-medium text-zinc-400">Voucher Code</label>
                      <input
                        value={voucherCode}
                        onChange={(e) => setVoucherCode(e.target.value)}
                        placeholder="XXXX-XXXX-XXXX"
                        className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm font-mono text-white placeholder-zinc-600 focus:border-indigo-500/50 focus:outline-none focus:ring-1 focus:ring-indigo-500/30"
                      />
                    </div>
                  )}

                  <button
                    onClick={handlePayment}
                    disabled={processing}
                    className="w-full rounded-xl py-3.5 text-sm font-semibold text-white transition-all disabled:opacity-50"
                    style={{ background: brandColor }}
                  >
                    Pay {formatCurrency(selectedPlan.price)} & Connect
                  </button>
                </div>
              )}

              {/* Stage: Processing */}
              {stage === 'processing' && (
                <div className="flex flex-col items-center justify-center py-16 animate-[fadeIn_0.3s_ease-out]">
                  <div className="relative">
                    <div className="h-16 w-16 rounded-full border-4 border-white/10" />
                    <Loader2 className="absolute inset-0 m-auto h-8 w-8 animate-spin" style={{ color: brandColor }} />
                  </div>
                  <p className="mt-6 text-sm font-medium text-white">Processing Payment...</p>
                  <p className="mt-1 text-xs text-zinc-500">
                    {paymentMethod === 'mobile_money' ? 'Waiting for M-Pesa STK push confirmation' :
                     paymentMethod === 'card' ? 'Authorizing card payment' : 'Validating voucher code'}
                  </p>
                </div>
              )}

              {/* Stage: Active */}
              {stage === 'active' && selectedPlan && (
                <div className="space-y-4 animate-[fadeIn_0.3s_ease-out]">
                  <div className="flex flex-col items-center pt-2">
                    <div className="flex h-16 w-16 items-center justify-center rounded-full" style={{ background: `${brandColor}20` }}>
                      <CheckCircle2 className="h-8 w-8" style={{ color: brandColor }} />
                    </div>
                    <p className="mt-3 text-base font-bold text-white">Internet Access Granted</p>
                    <p className="mt-0.5 text-xs text-zinc-500">You are now connected</p>
                  </div>

                  <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Clock className="h-4 w-4 text-zinc-500" />
                        <span className="text-xs text-zinc-400">Session Time Remaining</span>
                      </div>
                      <span className="font-mono text-lg font-bold text-white">{formatTime(timeRemaining)}</span>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
                      <div className="flex items-center gap-1.5 text-xs text-zinc-500">
                        <Gauge className="h-3.5 w-3.5" /> Download
                      </div>
                      <p className="mt-1 text-sm font-semibold text-white">{formatSpeed(selectedPlan.download_speed_kbps)}</p>
                    </div>
                    <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
                      <div className="flex items-center gap-1.5 text-xs text-zinc-500">
                        <Gauge className="h-3.5 w-3.5" /> Upload
                      </div>
                      <p className="mt-1 text-sm font-semibold text-white">{formatSpeed(selectedPlan.upload_speed_kbps)}</p>
                    </div>
                    <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
                      <div className="flex items-center gap-1.5 text-xs text-zinc-500">
                        <Smartphone className="h-3.5 w-3.5" /> Devices
                      </div>
                      <p className="mt-1 text-sm font-semibold text-white">{selectedPlan.simultaneous_devices}</p>
                    </div>
                    <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
                      <div className="flex items-center gap-1.5 text-xs text-zinc-500">
                        <Wifi className="h-3.5 w-3.5" /> Plan
                      </div>
                      <p className="mt-1 text-sm font-semibold text-white truncate">{selectedPlan.name}</p>
                    </div>
                  </div>

                  <div className="rounded-xl border border-white/10 bg-black/30 p-3">
                    <p className="text-[10px] text-zinc-600">Session Token</p>
                    <p className="mt-0.5 font-mono text-xs text-zinc-400 break-all">{sessionToken}</p>
                  </div>

                  <button
                    onClick={resetPortal}
                    className="w-full rounded-xl border border-white/10 py-3 text-sm font-medium text-zinc-300 hover:bg-white/5 transition-colors"
                  >
                    Start New Session
                  </button>
                </div>
              )}

              {/* Terms */}
              {stage !== 'active' && stage !== 'processing' && (
                <p className="mt-6 text-center text-[10px] leading-relaxed text-zinc-600 px-2">
                  {tenant.terms_of_service || 'By connecting you agree to our terms of service.'}
                </p>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
