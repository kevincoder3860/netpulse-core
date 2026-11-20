import { useEffect, useState } from 'react';
import { CheckCircle2, Clock, Loader2, Signal, Wifi, X } from 'lucide-react';
import { api } from '@/lib/api';
import { formatCurrency, formatDuration } from '@/lib/utils';
import type { HotspotPlan } from '@/lib/types';

interface MobilePortalPreviewProps {
  tenantId: string;
  businessName: string;
  headline: string;
  logoUrl: string;
  brandColor: string;
  hotspotName: string;
  nasId: string | null;
  plans: HotspotPlan[];
  onClose: () => void;
}

type PreviewPaymentState = 'idle' | 'submitting' | 'pending' | 'completed' | 'failed';

export default function MobilePortalPreview({
  tenantId,
  businessName,
  headline,
  logoUrl,
  brandColor,
  hotspotName,
  nasId,
  plans,
  onClose,
}: MobilePortalPreviewProps) {
  const [loginMethod, setLoginMethod] = useState<'voucher' | 'account'>('voucher');
  const activePlans = plans.filter((plan) => plan.is_active);
  const [paymentPlan, setPaymentPlan] = useState<HotspotPlan | null>(null);
  const [phoneNumber, setPhoneNumber] = useState('');
  const [paymentState, setPaymentState] = useState<PreviewPaymentState>('idle');
  const [paymentError, setPaymentError] = useState('');
  const [paymentMessage, setPaymentMessage] = useState('');
  const [checkoutRequestId, setCheckoutRequestId] = useState('');
  const [pollRun, setPollRun] = useState(0);
  const [previewMac] = useState(() => {
    const bytes = crypto.getRandomValues(new Uint8Array(5));
    return `02:${Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join(':')}`;
  });

  useEffect(() => {
    if (!checkoutRequestId || paymentState !== 'pending') return;
    let active = true;
    let attempts = 0;
    let timeout: ReturnType<typeof setTimeout>;

    const pollStatus = async () => {
      try {
        const result = await api.getTransactionStatus(checkoutRequestId);
        if (!active) return;
        if (result.status === 'COMPLETED' || result.status === 'completed') {
          setPaymentState('completed');
          setPaymentMessage('Payment confirmed. Your hotspot access is ready.');
          return;
        }
        if (result.status === 'FAILED' || result.status === 'failed') {
          setPaymentState('failed');
          setPaymentMessage('The payment was declined or cancelled. You can try again.');
          return;
        }
      } catch {
        if (!active) return;
        setPaymentMessage('Still checking Paystack for M-Pesa confirmation. Keep your phone nearby.');
      }

      attempts += 1;
      if (attempts >= 30) {
        setPaymentMessage('Payment is still pending. You can check again or close this preview.');
        return;
      }
      timeout = setTimeout(pollStatus, 4000);
    };

    void pollStatus();
    return () => {
      active = false;
      clearTimeout(timeout);
    };
  }, [checkoutRequestId, paymentState, pollRun]);

  const openPaymentPrompt = (plan: HotspotPlan) => {
    setPaymentPlan(plan);
    setPaymentState('idle');
    setPaymentError('');
    setPaymentMessage('');
    setCheckoutRequestId('');
    setPhoneNumber('');
  };

  const closePaymentPrompt = () => {
    setPaymentPlan(null);
    setPaymentState('idle');
    setCheckoutRequestId('');
    setPaymentError('');
    setPaymentMessage('');
  };

  const startPayment = async () => {
    if (!paymentPlan) return;
    if (!nasId) {
      setPaymentError('Connect a router to this workspace before testing payments.');
      return;
    }

    const digits = phoneNumber.trim().replace(/[\s()+-]/g, '');
    const normalizedPhone = /^0[17]\d{8}$/.test(digits) ? `254${digits.slice(1)}` : digits;
    if (!/^254[17]\d{8}$/.test(normalizedPhone)) {
      setPaymentError('Enter a valid Kenyan M-Pesa number, such as 0712345678.');
      return;
    }

    setPaymentState('submitting');
    setPaymentError('');
    setPaymentMessage('');
    try {
      const response = await api.initiatePaystackMobileMoney({
        tenant_id: tenantId,
        ...(nasId ? { nas_id: nasId } : {}),
        plan_id: paymentPlan.id,
        phone_number: normalizedPhone,
        mac_address: previewMac,
      });
      setCheckoutRequestId(response.checkout_request_id);
      setPaymentMessage(response.message || 'Check your phone for the Paystack M-Pesa prompt.');
      setPaymentState('pending');
    } catch (error) {
      setPaymentError(error instanceof Error ? error.message : 'Unable to start the Paystack M-Pesa payment.');
      setPaymentState('failed');
    }
  };

  const checkPaymentAgain = () => {
    setPaymentMessage('Checking payment status with Paystack...');
    setPollRun((run) => run + 1);
  };

  return (
    <section
      aria-label="Mobile captive portal preview"
      className="flex flex-col items-center rounded-2xl border border-white/10 bg-black/20 p-4 sm:p-6"
    >
      <div className="mb-4 flex w-full max-w-[375px] items-center justify-between">
        <div>
          <h4 className="text-sm font-semibold text-white">Mobile Preview</h4>
          <p className="mt-1 text-xs text-zinc-500">Updates as you edit your branding</p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close mobile preview"
          className="rounded-lg p-2 text-zinc-400 transition hover:bg-white/10 hover:text-white"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="w-full max-w-[395px] rounded-[2.8rem] border-[3px] border-zinc-700 bg-zinc-950 p-2 shadow-2xl shadow-black/50">
        <div className="relative aspect-[375/667] w-full overflow-hidden rounded-[2.25rem] bg-white text-zinc-900">
          <div className="absolute left-1/2 top-0 z-10 h-7 w-32 -translate-x-1/2 rounded-b-2xl bg-zinc-950" />
          <div className="flex h-full flex-col">
            <div className="flex shrink-0 items-center justify-between px-6 pb-2 pt-3 text-[10px] font-semibold text-zinc-800">
              <span>9:41</span>
              <div className="flex items-center gap-1">
                <Signal className="h-3 w-3" />
                <Wifi className="h-3 w-3" />
                <span className="text-[9px]">100%</span>
              </div>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto px-5 pb-5 pt-4" style={{ scrollbarWidth: 'none' }}>
              <header className="flex flex-col items-center text-center">
                {logoUrl ? (
                  <img
                    src={logoUrl}
                    alt={`${businessName} logo`}
                    className="h-14 w-14 rounded-2xl object-cover shadow-sm"
                  />
                ) : (
                  <div
                    className="flex h-14 w-14 items-center justify-center rounded-2xl text-xl font-bold text-white"
                    style={{ backgroundColor: brandColor }}
                  >
                    {businessName.trim().charAt(0).toUpperCase() || 'W'}
                  </div>
                )}
                <h3 className="mt-3 text-base font-bold leading-tight">
                  {headline || 'Welcome to our Wi-Fi'}
                </h3>
                <p className="mt-1 text-xs text-zinc-500">{businessName}</p>
                <div className="mt-3 inline-flex max-w-full items-center gap-1.5 rounded-full bg-zinc-100 px-3 py-1 text-[10px] font-medium text-zinc-600">
                  <Wifi className="h-3 w-3 shrink-0" />
                  <span className="truncate">{hotspotName}</span>
                </div>
              </header>

              <div className="mt-5">
                <p className="text-center text-xs font-semibold text-zinc-700">Choose a Wi-Fi plan</p>
                <div className="mt-2 space-y-2">
                  {activePlans.length > 0 ? activePlans.map((plan) => (
                    <button
                      type="button"
                      key={plan.id}
                      onClick={() => openPaymentPrompt(plan)}
                      className="flex w-full items-center justify-between rounded-xl border bg-white px-3 py-2.5 text-left shadow-sm"
                      style={{ borderColor: '#e4e4e7' }}
                    >
                      <div className="min-w-0">
                        <p className="truncate text-xs font-semibold">{plan.name}</p>
                        <p className="mt-0.5 flex items-center gap-1 text-[10px] text-zinc-500">
                          <Clock className="h-3 w-3" />
                          {formatDuration(plan.duration_minutes)}
                        </p>
                      </div>
                      <span className="ml-2 shrink-0 text-xs font-bold" style={{ color: brandColor }}>
                        {formatCurrency(plan.price)}
                      </span>
                    </button>
                  )) : (
                    <p className="rounded-xl border border-dashed border-zinc-300 px-3 py-3 text-center text-[10px] text-zinc-500">
                      No active plans available
                    </p>
                  )}
                </div>
              </div>

              <div className="mt-4">
                <div className="grid grid-cols-2 rounded-lg bg-zinc-100 p-1 text-[10px] font-semibold">
                  <button
                    type="button"
                    onClick={() => setLoginMethod('voucher')}
                    className={`rounded-md px-2 py-1.5 transition ${loginMethod === 'voucher' ? 'bg-white text-zinc-900 shadow-sm' : 'text-zinc-500'}`}
                  >
                    Voucher
                  </button>
                  <button
                    type="button"
                    onClick={() => setLoginMethod('account')}
                    className={`rounded-md px-2 py-1.5 transition ${loginMethod === 'account' ? 'bg-white text-zinc-900 shadow-sm' : 'text-zinc-500'}`}
                  >
                    Username &amp; password
                  </button>
                </div>
                <div className="mt-2 space-y-2">
                  {loginMethod === 'voucher' ? (
                    <input
                      aria-label="Voucher code preview"
                      readOnly
                      placeholder="Enter voucher code"
                      className="w-full rounded-xl border border-zinc-200 bg-white px-3 py-2.5 text-xs outline-none placeholder:text-zinc-400"
                    />
                  ) : (
                    <>
                      <input
                        aria-label="Username preview"
                        readOnly
                        placeholder="Username"
                        className="w-full rounded-xl border border-zinc-200 bg-white px-3 py-2.5 text-xs outline-none placeholder:text-zinc-400"
                      />
                      <input
                        aria-label="Password preview"
                        readOnly
                        type="password"
                        placeholder="Password"
                        className="w-full rounded-xl border border-zinc-200 bg-white px-3 py-2.5 text-xs outline-none placeholder:text-zinc-400"
                      />
                    </>
                  )}
                  <button
                    type="button"
                    className="w-full rounded-xl px-4 py-2.5 text-xs font-bold text-white shadow-sm"
                    style={{ backgroundColor: brandColor }}
                  >
                    Connect / Login
                  </button>
                </div>
              </div>

              <p className="mt-3 text-center text-[9px] text-zinc-400">
                Secure Wi-Fi access by {businessName}
              </p>
            </div>
          </div>
          {paymentPlan && (
            <div className="absolute inset-0 z-20 flex flex-col overflow-y-auto bg-white px-5 pb-6 pt-12 text-zinc-900">
              <button
                type="button"
                onClick={closePaymentPrompt}
                aria-label="Close M-Pesa payment prompt"
                className="absolute right-4 top-4 rounded-lg p-2 text-zinc-500 hover:bg-zinc-100"
              >
                <X className="h-4 w-4" />
              </button>
              <div className="my-auto">
                <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-emerald-50 text-emerald-700">
                  <span className="text-sm font-extrabold">M</span>
                </div>
                <h3 className="mt-4 text-center text-base font-bold">Pay with Paystack M-Pesa</h3>
                <p className="mt-1 text-center text-xs text-zinc-500">{paymentPlan.name}</p>
                <p className="mt-2 text-center text-xl font-bold" style={{ color: brandColor }}>
                  {formatCurrency(paymentPlan.price)}
                </p>

                {paymentState === 'completed' ? (
                  <div className="mt-6 rounded-xl bg-emerald-50 p-4 text-center">
                    <CheckCircle2 className="mx-auto h-8 w-8 text-emerald-600" />
                    <p className="mt-2 text-sm font-semibold text-emerald-800">Payment confirmed</p>
                    <p className="mt-1 text-xs text-emerald-700">{paymentMessage}</p>
                  </div>
                ) : (
                  <>
                    <label htmlFor="preview-mpesa-phone" className="mt-6 block text-xs font-semibold text-zinc-700">
                      M-Pesa phone number
                    </label>
                    <input
                      id="preview-mpesa-phone"
                      type="tel"
                      inputMode="tel"
                      autoComplete="tel"
                      value={phoneNumber}
                      disabled={paymentState === 'pending'}
                      onChange={(event) => setPhoneNumber(event.target.value)}
                      placeholder="0712 345 678"
                      className="mt-2 w-full rounded-xl border border-zinc-200 bg-white px-3 py-3 text-sm outline-none focus:border-emerald-500 disabled:bg-zinc-100"
                    />
                    <p className="mt-2 text-[10px] leading-relaxed text-zinc-500">
                      {paymentState === 'pending'
                        ? paymentMessage || 'Check your phone for the M-Pesa prompt...'
                        : 'An STK Push will be sent to this number.'}
                    </p>
                    {paymentState === 'failed' && paymentMessage && (
                      <p role="status" className="mt-2 text-xs text-rose-700">{paymentMessage}</p>
                    )}
                    {paymentError && (
                      <p role="alert" className="mt-2 rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-700">
                        {paymentError}
                      </p>
                    )}
                    {paymentState !== 'pending' && (
                      <p className="mt-2 text-[10px] text-amber-700">
                        Production gateway settings may send a real payment request. Use Sandbox for tests.
                      </p>
                    )}
                    {paymentState === 'pending' ? (
                      <div className="mt-5 space-y-3">
                        <div className="flex items-center justify-center gap-2 text-xs font-medium text-emerald-700">
                          <Loader2 className="h-4 w-4 animate-spin" />
                          Waiting for Paystack confirmation
                        </div>
                        {paymentMessage.includes('still pending') && (
                          <button
                            type="button"
                            onClick={checkPaymentAgain}
                            className="w-full rounded-xl border border-zinc-200 px-4 py-2.5 text-xs font-semibold text-zinc-700"
                          >
                            Check status again
                          </button>
                        )}
                      </div>
                    ) : (
                      <button
                        type="button"
                        onClick={startPayment}
                        disabled={paymentState === 'submitting'}
                        className="mt-4 flex w-full items-center justify-center gap-2 rounded-xl px-4 py-3 text-xs font-bold text-white disabled:cursor-wait disabled:opacity-70"
                        style={{ backgroundColor: brandColor }}
                      >
                        {paymentState === 'submitting' && <Loader2 className="h-4 w-4 animate-spin" />}
                        {paymentState === 'submitting' ? 'Sending STK Push...' : 'Pay with STK Push'}
                      </button>
                    )}
                  </>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
