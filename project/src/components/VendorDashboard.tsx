import { useState, useEffect, useCallback } from 'react';
import {
  api, type AnalyticsData, type RouterMetrics,
  type VoucherRecord, type RechargeRecord,
} from '@/lib/api';
import { useToast } from '@/components/Toast';
import Modal from '@/components/Modal';
import MetricCard from '@/components/MetricCard';
import StatusBadge from '@/components/StatusBadge';
import MobilePortalPreview from '@/components/MobilePortalPreview';
import { useTelemetry } from '@/hooks/useTelemetry';
import {
  formatCurrency, formatNumber, formatDuration, formatSpeed,
  formatBytes, timeAgo, formatDateTime, formatDate, generateMacAddress, generateSecret,
} from '@/lib/utils';
import type {
  Tenant, Nas, HotspotPlan, Transaction, StaffMember, StaffRole,
  Customer, ActiveSession, Invoice, SupportTicket,
} from '@/lib/types';
import {
  DollarSign, Wallet, Users, Router as RouterIcon, Plus, Wifi,
  Copy, Check, Palette, Zap, Activity, TrendingUp, Ticket,
  CircleDollarSign, FileText, Layers, Settings, MessageSquare, Loader2,
  Search, Trash2, ExternalLink, ShieldCheck, AlertTriangle,
  Printer, Clock, Power, Send, RefreshCw, Download, Radio, CreditCard,
  Smartphone, Pencil,
} from 'lucide-react';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  BarChart, Bar, Legend,
} from 'recharts';

interface VendorDashboardProps {
  tenant: Tenant;
  onBrandingChange?: () => void;
}

type VendorTab =
  | 'dashboard'
  | 'customers'
  | 'hotspot_pppoe'
  | 'plans_vouchers'
  | 'subscriptions_payments'
  | 'invoices_routers'
  | 'tickets_reports';

export default function VendorDashboard({ tenant, onBrandingChange }: VendorDashboardProps) {
  const { toast } = useToast();
  const authClaims = api.getAuthClaims();
  const canManagePayments = authClaims?.role === 'VENDOR' || authClaims?.staff_role === 'MANAGER';
  const [activeTab, setActiveTab] = useState<VendorTab>('dashboard');
  const [loading, setLoading] = useState(true);

  // Core Data
  const [routers, setRouters] = useState<Nas[]>([]);
  const [routerLoading, setRouterLoading] = useState(true);
  const [routerError, setRouterError] = useState<string | null>(null);
  const [plans, setPlans] = useState<HotspotPlan[]>([]);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [activeSessions, setActiveSessions] = useState<ActiveSession[]>([]);
  const [vouchers, setVouchers] = useState<VoucherRecord[]>([]);
  const [recharges, setRecharges] = useState<RechargeRecord[]>([]);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [tickets, setTickets] = useState<SupportTicket[]>([]);
  const [staff, setStaff] = useState<StaffMember[]>([]);

  // Telemetry
  const { telemetryData, trafficSamples, connected } = useTelemetry(tenant.id);

  const fetchRouters = useCallback(async () => {
    setRouterLoading(true);
    setRouterError(null);
    try {
      setRouters(await api.getRouters(tenant.id));
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to load routers.';
      setRouterError(message);
      toast(message, 'error');
    } finally {
      setRouterLoading(false);
    }
  }, [tenant.id, toast]);

  // Hotspot & PPPoE Sub-module tab
  const [hotspotSubTab, setHotspotSubTab] = useState<'sessions' | 'pppoe' | 'branding'>('sessions');

  // Plans & Vouchers Sub-module tab
  const [plansVouchersSubTab, setPlansVouchersSubTab] = useState<'plans' | 'vouchers'>('plans');

  // Invoices & Routers Sub-module tab
  const [invoicesRoutersSubTab, setInvoicesRoutersSubTab] = useState<'invoices' | 'routers'>('invoices');

  // Tickets & Reports Sub-module tab
  const [ticketsReportsSubTab, setTicketsReportsSubTab] = useState<'tickets' | 'reports'>('tickets');

  // Search & Filter States
  const [customerSearch, setCustomerSearch] = useState('');
  const [customerTypeFilter, setCustomerTypeFilter] = useState<'all' | 'hotspot' | 'pppoe'>('all');
  const [txSearch, setTxSearch] = useState('');
  const [txStatusFilter, setTxStatusFilter] = useState('all');

  // Modals
  const [showRouterModal, setShowRouterModal] = useState(false);
  const [creatingRouter, setCreatingRouter] = useState(false);
  const [editingRouter, setEditingRouter] = useState<Nas | null>(null);
  const [deletingRouterId, setDeletingRouterId] = useState<string | null>(null);
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

  const [showProvisionModal, setShowProvisionModal] = useState(false);
  const [selectedRouterForProvision, setSelectedRouterForProvision] = useState<Nas | null>(null);
  const [provisioningBusy, setProvisioningBusy] = useState(false);
  const [selectedMetricsRouter, setSelectedMetricsRouter] = useState<Nas | null>(null);
  const [routerMetrics, setRouterMetrics] = useState<RouterMetrics | null>(null);
  const [routerMetricsLoading, setRouterMetricsLoading] = useState(false);
  const [routerMetricsError, setRouterMetricsError] = useState<string | null>(null);
  const [routerMetricsStatus, setRouterMetricsStatus] = useState<'connecting' | 'online' | 'offline'>('offline');
  const [routerMetricsRefreshKey, setRouterMetricsRefreshKey] = useState(0);

  const [showScriptModal, setShowScriptModal] = useState(false);
  const [activeScript, setActiveScript] = useState('');
  const [scriptCopied, setScriptCopied] = useState(false);

  const [showPlanModal, setShowPlanModal] = useState(false);
  const [creatingPlan, setCreatingPlan] = useState(false);
  const [togglingPlanId, setTogglingPlanId] = useState<string | null>(null);
  const [planForm, setPlanForm] = useState({
    name: '',
    price: '100',
    duration_value: '60',
    duration_unit: 'minutes' as 'minutes' | 'hours' | 'days',
    download_speed_kbps: '5120',
    upload_speed_kbps: '2048',
    simultaneous_devices: '1',
  });

  const [showCustomerModal, setShowCustomerModal] = useState(false);
  const [customerForm, setCustomerForm] = useState({
    name: '',
    phone_number: '',
    username: '',
    service_type: 'hotspot' as 'hotspot' | 'pppoe',
    plan_name: '',
    pppoe_password: '',
    portal_password: '',
    mac_address: '',
  });
  const [creatingCustomer, setCreatingCustomer] = useState(false);
  const [disconnectingSessionId, setDisconnectingSessionId] = useState<string | null>(null);

  const [showVoucherModal, setShowVoucherModal] = useState(false);
  const [voucherForm, setVoucherForm] = useState({ count: '25', valid_days: '30' });
  const [generatingVouchers, setGeneratingVouchers] = useState(false);
  const [deletingUsedVouchers, setDeletingUsedVouchers] = useState(false);
  const [showBatchPrintModal, setShowBatchPrintModal] = useState(false);

  const [showInvoiceModal, setShowInvoiceModal] = useState(false);
  const [invoiceForm, setInvoiceForm] = useState({
    customer_name: '',
    customer_phone: '',
    plan_name: '',
    amount: '1500',
    due_days: '7',
  });
  const [creatingInvoice, setCreatingInvoice] = useState(false);

  const [showTicketModal, setShowTicketModal] = useState(false);
  const [ticketForm, setTicketForm] = useState({
    customer_name: '',
    customer_phone: '',
    subject: '',
    description: '',
    priority: 'MEDIUM' as SupportTicket['priority'],
  });

  const [activeTicket, setActiveTicket] = useState<SupportTicket | null>(null);
  const [ticketReplyText, setTicketReplyText] = useState('');
  const [creatingTicket, setCreatingTicket] = useState(false);
  const [sendingTicketReply, setSendingTicketReply] = useState(false);

  // Branding state
  const [branding, setBranding] = useState({
    logo_url: tenant.logo_url || '',
    brand_color: tenant.brand_color || '#06b6d4',
    welcome_headline: tenant.welcome_headline || '',
    terms_of_service: tenant.terms_of_service || '',
  });
  const [savingBranding, setSavingBranding] = useState(false);
  const [showMobilePreview, setShowMobilePreview] = useState(false);
  const [paystackSecretKey, setPaystackSecretKey] = useState('');
  const [paystackSecretKeySet, setPaystackSecretKeySet] = useState(Boolean(tenant.paystack_secret_key_set));
  const [paystackBillingEmail, setPaystackBillingEmail] = useState(tenant.billing_email || tenant.email);
  const [savingPaystackConfiguration, setSavingPaystackConfiguration] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const failures: string[] = [];
      const loadList = async <T,>(request: Promise<T[]>, resource: string): Promise<T[]> => {
        try {
          return await request;
        } catch (error) {
          failures.push(resource);
          console.error(`Failed to load ${resource} for tenant ${tenant.id}`, error);
          return [];
        }
      };
      const [
        plansData, transactionsData,
        customersData, sessionsData, vouchersData, rechargesData,
        invoicesData, ticketsData, staffData,
      ] = await Promise.all([
        loadList(api.getPlans(tenant.id), 'plans'),
        loadList(api.getTransactions(tenant.id), 'transactions'),
        loadList(api.getCustomers(tenant.id), 'customers'),
        loadList(api.getActiveSessions(tenant.id), 'active sessions'),
        loadList(api.getVouchers(tenant.id), 'vouchers'),
        loadList(api.getRecharges(tenant.id), 'subscriptions'),
        loadList(api.getInvoices(tenant.id), 'invoices'),
        loadList(api.getTickets(tenant.id), 'tickets'),
        loadList(api.getStaff(), 'staff'),
      ]);
      setPlans(plansData);
      setTransactions(transactionsData);
      setCustomers(customersData);
      setActiveSessions(sessionsData);
      setVouchers(vouchersData);
      setRecharges(rechargesData);
      setInvoices(invoicesData);
      setTickets(ticketsData);
      setStaff(staffData);
      if (failures.length) {
        toast(`Some dashboard data could not be loaded: ${failures.join(', ')}.`, 'error');
      }
    } catch {
      toast('Failed to load vendor operational data', 'error');
    } finally {
      setLoading(false);
    }
  }, [tenant.id, toast]);

  const refreshSubscriberAndPaymentData = useCallback(async () => {
    try {
      const [transactionsData, customersData, rechargesData] = await Promise.all([
        api.getTransactions(tenant.id),
        api.getCustomers(tenant.id),
        api.getRecharges(tenant.id),
      ]);
      setTransactions(transactionsData);
      setCustomers(customersData);
      setRecharges(rechargesData);
    } catch (error) {
      console.error(`Failed to refresh tenant ${tenant.id} subscriber and payment data`, error);
    }
  }, [tenant.id]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    const refreshWhenVisible = () => {
      if (!document.hidden) void refreshSubscriberAndPaymentData();
    };
    const intervalId = window.setInterval(refreshWhenVisible, 15000);
    window.addEventListener('focus', refreshWhenVisible);
    document.addEventListener('visibilitychange', refreshWhenVisible);
    return () => {
      window.clearInterval(intervalId);
      window.removeEventListener('focus', refreshWhenVisible);
      document.removeEventListener('visibilitychange', refreshWhenVisible);
    };
  }, [refreshSubscriberAndPaymentData]);

  useEffect(() => {
    void fetchRouters();
  }, [fetchRouters]);

  useEffect(() => {
    if (connected) void fetchRouters();
  }, [connected, fetchRouters]);

  useEffect(() => {
    setPaystackSecretKey('');
    setPaystackSecretKeySet(Boolean(tenant.paystack_secret_key_set));
    setPaystackBillingEmail(tenant.billing_email || tenant.email);
  }, [tenant.id, tenant.billing_email, tenant.email, tenant.paystack_secret_key_set]);

  useEffect(() => {
    if (!selectedMetricsRouter) {
      setRouterMetrics(null);
      setRouterMetricsError(null);
      setRouterMetricsStatus('offline');
      return;
    }

    let active = true;
    let timeoutId: number | undefined;
    const fetchMetrics = async () => {
      if (!selectedMetricsRouter.is_online) {
        setRouterMetricsStatus('offline');
        setRouterMetricsError('This router is currently marked offline.');
        return;
      }

      setRouterMetricsLoading(true);
      setRouterMetricsStatus('connecting');
      try {
        const metrics = await api.getRouterMetrics(selectedMetricsRouter.id);
        if (active) {
          setRouterMetrics(metrics);
          setRouterMetricsError(null);
          setRouterMetricsStatus('online');
        }
      } catch (error) {
        if (active) {
          setRouterMetricsError(error instanceof Error ? error.message : 'Unable to load router metrics.');
          setRouterMetricsStatus('offline');
        }
      } finally {
        if (active) {
          setRouterMetricsLoading(false);
          timeoutId = window.setTimeout(fetchMetrics, 15000);
        }
      }
    };

    fetchMetrics();
    return () => {
      active = false;
      if (timeoutId !== undefined) window.clearTimeout(timeoutId);
    };
  }, [selectedMetricsRouter, routerMetricsRefreshKey]);

  const openRouterMetrics = (router: Nas) => {
    setRouterMetrics(null);
    setRouterMetricsError(null);
    setRouterMetricsStatus(router.is_online ? 'connecting' : 'offline');
    setSelectedMetricsRouter(router);
  };

  const refreshRouterMetrics = () => {
    if (!selectedMetricsRouter?.is_online || routerMetricsLoading) return;
    setRouterMetricsStatus('connecting');
    setRouterMetricsRefreshKey((key) => key + 1);
  };

  // Financial Computations
  const todayTx = transactions.filter((t) => {
    const d = new Date(t.created_at);
    const now = new Date();
    return d.getDate() === now.getDate() && d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear();
  });
  const dailyGross = todayTx.reduce((s, t) => s + Number(t.gross_amount || 0), 0);
  const monthlyGross = transactions.reduce((s, t) => s + Number(t.gross_amount || 0), 0);
  const netEarnings = transactions.reduce((s, t) => s + Number(t.vendor_net_amount || 0), 0);
  const onlineRouters = routers.filter((r) => r.is_online).length;

  // Actions
  const handleKickSession = async (sessionId: string, username: string) => {
    if (disconnectingSessionId !== null) return;
    setDisconnectingSessionId(sessionId);
    try {
      const res = await api.disconnectSession(sessionId);
      setActiveSessions((prev) => prev.filter((s) => s.id !== sessionId));
      toast(res.message || `Session for ${username} disconnected`);
    } catch {
      toast('Unable to disconnect session', 'error');
    } finally {
      setDisconnectingSessionId(null);
    }
  };

  const handleCreateCustomer = async () => {
    if (creatingCustomer) return;
    if (!customerForm.name || !customerForm.phone_number || customerForm.portal_password.length < 8) {
      toast('Provide a customer name, phone, and portal password (at least 8 characters)', 'error');
      return;
    }
    setCreatingCustomer(true);
    try {
      const created = await api.createCustomer({
        tenant_id: tenant.id,
        name: customerForm.name,
        phone_number: customerForm.phone_number,
        username: customerForm.username || customerForm.phone_number,
        service_type: customerForm.service_type,
        plan_name: customerForm.plan_name || 'Standard Plan',
        pppoe_password: customerForm.pppoe_password,
        portal_password: customerForm.portal_password,
        mac_address: customerForm.mac_address || generateMacAddress(),
        status: 'active',
      });
      setCustomers((prev) => [created, ...prev]);
      setShowCustomerModal(false);
      setCustomerForm({ name: '', phone_number: '', username: '', service_type: 'hotspot', plan_name: '', pppoe_password: '', portal_password: '', mac_address: '' });
      toast(`Customer ${created.name} added!`);
    } catch {
      toast('Failed to add customer', 'error');
    } finally {
      setCreatingCustomer(false);
    }
  };

  const openCreateRouter = () => {
    setEditingRouter(null);
    setNewRouter({
      nasname: '',
      shortname: '',
      nas_ip: '10.10.0.10',
      api_port: '8728',
      api_username: 'admin',
      api_password: '',
      radius_server_ip: '10.10.0.5',
      shared_secret: '',
    });
    setShowRouterModal(true);
  };

  const openEditRouter = (router: Nas) => {
    setEditingRouter(router);
    setNewRouter({
      nasname: router.nasname,
      shortname: router.shortname,
      nas_ip: router.nas_ip || '',
      api_port: String(router.api_port || 8728),
      api_username: router.api_username || '',
      api_password: '',
      radius_server_ip: router.radius_server_ip || '',
      shared_secret: '',
    });
    setShowRouterModal(true);
  };

  const handleSaveRouter = async () => {
    if (!newRouter.nasname.trim() || !newRouter.shortname.trim() || (!editingRouter && !newRouter.shared_secret.trim())) {
      toast('Router name, location label, and RADIUS shared secret are required', 'error');
      return;
    }
    const apiPort = Number(newRouter.api_port);
    if (!Number.isInteger(apiPort) || apiPort < 1 || apiPort > 65535) {
      toast('Enter a valid RouterOS API port (1–65535)', 'error');
      return;
    }

    setCreatingRouter(true);
    try {
      if (editingRouter) {
        const payload: Record<string, string | number> = {
          nasname: newRouter.nasname.trim(),
          shortname: newRouter.shortname.trim(),
          nas_ip: newRouter.nas_ip.trim(),
          api_port: apiPort,
          api_username: newRouter.api_username.trim(),
          radius_server_ip: newRouter.radius_server_ip.trim(),
        };
        if (newRouter.api_password) payload.api_password = newRouter.api_password;
        if (newRouter.shared_secret) payload.shared_secret = newRouter.shared_secret;
        const updated = await api.updateRouter(editingRouter.id, payload);
        setRouters((current) => current.map((router) => router.id === updated.id ? updated : router));
        toast(`Router ${updated.nasname} updated successfully`);
      } else {
        const created = await api.createRouter({
          tenant: tenant.id,
          nasname: newRouter.nasname.trim(),
          shortname: newRouter.shortname.trim(),
          nas_ip: newRouter.nas_ip.trim(),
          secret: newRouter.shared_secret.trim(),
          shared_secret: newRouter.shared_secret.trim(),
          api_port: apiPort,
          api_username: newRouter.api_username.trim(),
          api_password: newRouter.api_password,
          radius_server_ip: newRouter.radius_server_ip.trim(),
        });
        setRouters((current) => [created, ...current.filter((router) => router.id !== created.id)]);
        toast(`Router ${created.nasname} bound successfully`);
      }
      setShowRouterModal(false);
      setEditingRouter(null);
      setNewRouter({
        nasname: '',
        shortname: '',
        nas_ip: '10.10.0.10',
        api_port: '8728',
        api_username: 'admin',
        api_password: '',
        radius_server_ip: '10.10.0.5',
        shared_secret: '',
      });
    } catch (error) {
      toast(error instanceof Error ? error.message : 'Unable to save router', 'error');
    } finally {
      setCreatingRouter(false);
    }
  };

  const handleDeleteRouter = async (router: Nas) => {
    if (!window.confirm(`Delete router "${router.nasname}"? This cannot be undone.`)) return;
    setDeletingRouterId(router.id);
    try {
      await api.deleteRouter(router.id);
      setRouters((current) => current.filter((item) => item.id !== router.id));
      toast(`Router ${router.nasname} deleted`);
    } catch (error) {
      toast(error instanceof Error ? error.message : 'Unable to delete router', 'error');
    } finally {
      setDeletingRouterId(null);
    }
  };

  const handleGenerateVouchers = async () => {
    setGeneratingVouchers(true);
    try {
      const count = Number(voucherForm.count) || 10;
      const validDays = Number(voucherForm.valid_days) || 30;
      const created = await api.generateVouchers({
        tenant: tenant.id,
        count,
        valid_days: validDays,
      });
      setVouchers((prev) => [...created, ...prev]);
      setShowVoucherModal(false);
      toast(`Generated ${created.length} new prepaid vouchers!`);
    } catch {
      toast('Failed to generate vouchers', 'error');
    } finally {
      setGeneratingVouchers(false);
    }
  };

  const handleDeleteUsedVouchers = async () => {
    if (deletingUsedVouchers) return;
    setDeletingUsedVouchers(true);
    try {
      const res = await api.deleteUsedVouchers();
      setVouchers((prev) => prev.filter((v) => v.status !== 'USED'));
      toast(`Deleted ${res.deleted} used vouchers`);
    } catch {
      toast('Failed to delete used vouchers', 'error');
    } finally {
      setDeletingUsedVouchers(false);
    }
  };

  const handleCreatePlan = async () => {
    if (!planForm.name || !planForm.price) {
      toast('Please provide plan name and price', 'error');
      return;
    }
    setCreatingPlan(true);
    try {
      const created = await api.createPlan({
        tenant: tenant.id,
        name: planForm.name,
        price: Number(planForm.price),
        duration_value: Number(planForm.duration_value),
        duration_unit: planForm.duration_unit,
        duration_minutes: Number(planForm.duration_value) * (
          planForm.duration_unit === 'days' ? 1440 :
          planForm.duration_unit === 'hours' ? 60 : 1
        ),
        download_speed_kbps: Number(planForm.download_speed_kbps),
        upload_speed_kbps: Number(planForm.upload_speed_kbps),
        simultaneous_devices: Number(planForm.simultaneous_devices),
        is_active: true,
      });
      setPlans((prev) => [created, ...prev]);
      setShowPlanModal(false);
      setPlanForm({ name: '', price: '100', duration_value: '60', duration_unit: 'minutes', download_speed_kbps: '5120', upload_speed_kbps: '2048', simultaneous_devices: '1' });
      toast(`Service plan "${created.name}" created!`);
    } catch {
      toast('Failed to create service plan', 'error');
    } finally {
      setCreatingPlan(false);
    }
  };

  const handleTogglePlan = async (plan: HotspotPlan) => {
    if (togglingPlanId !== null) return;
    setTogglingPlanId(plan.id);
    try {
      const updated = await api.updatePlan(plan.id, { is_active: !plan.is_active });
      setPlans((prev) => prev.map((p) => (p.id === plan.id ? { ...p, is_active: updated.is_active } : p)));
      toast(`Plan "${plan.name}" updated`);
    } catch {
      toast('Failed to update plan status', 'error');
    } finally {
      setTogglingPlanId(null);
    }
  };

  const handleCreateInvoice = async () => {
    if (creatingInvoice) return;
    if (!invoiceForm.customer_name || !invoiceForm.amount) {
      toast('Please enter customer and amount', 'error');
      return;
    }
    setCreatingInvoice(true);
    try {
      const days = Number(invoiceForm.due_days) || 7;
      const created = await api.createInvoice({
        tenant_id: tenant.id,
        customer_name: invoiceForm.customer_name,
        customer_phone: invoiceForm.customer_phone,
        plan_name: invoiceForm.plan_name || 'Broadband Subscription',
        amount: Number(invoiceForm.amount),
        date: new Date().toISOString().slice(0, 10),
        due_date: new Date(Date.now() + 86400000 * days).toISOString().slice(0, 10),
        status: 'UNPAID',
      });
      setInvoices((prev) => [created, ...prev]);
      setShowInvoiceModal(false);
      setInvoiceForm({ customer_name: '', customer_phone: '', plan_name: '', amount: '1500', due_days: '7' });
      toast(`Invoice #${created.invoice_number} generated!`);
    } catch {
      toast('Failed to generate invoice', 'error');
    } finally {
      setCreatingInvoice(false);
    }
  };

  const handleCreateTicket = async () => {
    if (creatingTicket) return;
    if (!ticketForm.customer_name || !ticketForm.subject) {
      toast('Please fill in customer and subject', 'error');
      return;
    }
    setCreatingTicket(true);
    try {
      const created = await api.createTicket({
        tenant_id: tenant.id,
        customer_name: ticketForm.customer_name,
        customer_phone: ticketForm.customer_phone,
        subject: ticketForm.subject,
        description: ticketForm.description,
        priority: ticketForm.priority,
      });
      setTickets((prev) => [created, ...prev]);
      setShowTicketModal(false);
      setTicketForm({ customer_name: '', customer_phone: '', subject: '', description: '', priority: 'MEDIUM' });
      toast(`Support ticket #${created.ticket_number} created!`);
    } catch {
      toast('Failed to create ticket', 'error');
    } finally {
      setCreatingTicket(false);
    }
  };

  const handleSendTicketReply = async () => {
    if (sendingTicketReply || !activeTicket || !ticketReplyText.trim()) return;
    setSendingTicketReply(true);
    try {
      const msg = await api.addTicketMessage(activeTicket.id, ticketReplyText.trim());
      setActiveTicket({
        ...activeTicket,
        messages: [...activeTicket.messages, msg],
      });
      setTicketReplyText('');
      toast('Reply sent to subscriber');
    } catch {
      toast('Failed to send reply', 'error');
    } finally {
      setSendingTicketReply(false);
    }
  };

  const handleSaveBranding = async () => {
    setSavingBranding(true);
    try {
      await api.updateTenant(tenant.id, branding);
      if (onBrandingChange) onBrandingChange();
      toast('Branding & Captive Portal settings updated!');
    } catch {
      toast('Failed to save branding', 'error');
    } finally {
      setSavingBranding(false);
    }
  };

  const handleSavePaystackConfiguration = async () => {
    if (!paystackBillingEmail.trim()) {
      toast('Enter the billing email for Paystack receipts', 'error');
      return;
    }
    if (!paystackSecretKey.trim() && !paystackSecretKeySet) {
      toast('Enter your Paystack secret key before saving', 'error');
      return;
    }

    setSavingPaystackConfiguration(true);
    try {
      const saved = await api.updateTenant(tenant.id, {
        billing_email: paystackBillingEmail.trim(),
        paystack_secret_key: paystackSecretKey.trim(),
      });
      setPaystackSecretKeySet(Boolean(saved.paystack_secret_key_set) || paystackSecretKey.trim().length > 0);
      setPaystackSecretKey('');
      onBrandingChange?.();
      toast('Paystack M-Pesa settings saved securely.');
    } catch (error) {
      toast(error instanceof Error ? error.message : 'Unable to save Paystack settings', 'error');
    } finally {
      setSavingPaystackConfiguration(false);
    }
  };

  // Router Provision & Script
  const handleViewScript = async (router: Nas) => {
    try {
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

  const handleProvisionRouter = async () => {
    if (!selectedRouterForProvision) return;
    setProvisioningBusy(true);
    try {
      await api.provisionRouter(selectedRouterForProvision.id, {
        nas_ip: selectedRouterForProvision.nas_ip || '10.10.0.10',
        api_port: 8728,
        api_username: 'admin',
        api_password: '',
      });
      toast(`Router ${selectedRouterForProvision.nasname} provisioned and verified online!`);
      setShowProvisionModal(false);
      fetchData();
    } catch (err) {
      toast(err instanceof Error ? err.message : 'Provisioning failed', 'error');
    } finally {
      setProvisioningBusy(false);
    }
  };

  // Live Traffic Samples
  const chartData = trafficSamples.length > 0
    ? trafficSamples.map((s) => ({
        time: new Date(s.timestamp).toLocaleTimeString([], { minute: '2-digit', second: '2-digit' }),
        tx: s.tx_kbps,
        rx: s.rx_kbps,
      }))
    : Array.from({ length: 12 }, (_, i) => ({
        time: `${i * 2}:00`,
        tx: Math.round(Math.random() * 2500 + 500),
        rx: Math.round(Math.random() * 4500 + 1200),
      }));

  if (loading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="h-9 w-9 animate-spin rounded-full border-2 border-white/10 border-t-cyan-400" />
          <p className="text-xs text-zinc-500 font-medium">Synchronizing WISP operational workspace...</p>
        </div>
      </div>
    );
  }

  const activeSubscriberCount = new Set(
    recharges.filter((recharge) => recharge.status === 'ACTIVE').map((recharge) => recharge.username),
  ).size;
  const tabsConfig: { id: VendorTab; label: string; icon: typeof Activity; badge?: string }[] = [
    { id: 'dashboard', label: 'Dashboard', icon: Activity },
    { id: 'customers', label: 'Customers', icon: Users, badge: String(customers.length) },
    { id: 'hotspot_pppoe', label: 'Hotspot & PPPoE', icon: Wifi, badge: String(activeSubscriberCount) },
    { id: 'plans_vouchers', label: 'Plans & Vouchers', icon: Ticket, badge: String(plans.length) },
    { id: 'subscriptions_payments', label: 'Subscriptions & Payments', icon: CreditCard, badge: String(transactions.length) },
    { id: 'invoices_routers', label: 'Invoices & Routers', icon: RouterIcon, badge: `${onlineRouters}/${routers.length}` },
    { id: 'tickets_reports', label: 'Tickets & Reports', icon: MessageSquare, badge: String(tickets.filter((t) => t.status === 'OPEN').length) },
  ];

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col gap-4 border-b border-white/10 pb-5 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span
              className="flex h-6 items-center rounded-full px-2.5 text-[11px] font-semibold uppercase tracking-wider text-white shadow border border-white/20"
              style={{ background: tenant.brand_color || '#06b6d4' }}
            >
              WISP Operations
            </span>
            <span className="text-xs text-zinc-500">{tenant.business_name}</span>
          </div>
          <h1 className="mt-2 text-2xl font-bold tracking-tight text-white sm:text-3xl">{tenant.business_name} Workspace</h1>
          <p className="mt-1 text-xs text-zinc-400">Subscriber management, captive portal sessions, billing, and Mikrotik network telemetry</p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <div className={`flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs ${connected ? 'text-emerald-300' : 'text-zinc-400'}`}>
            <span className={`h-2 w-2 rounded-full ${connected ? 'bg-emerald-400 animate-pulse' : 'bg-zinc-500'}`} />
            {connected ? 'Live WebSocket Telemetry' : 'Telemetry Polling'}
          </div>
          <button
            type="button"
            onClick={() => setShowMobilePreview(true)}
            className="flex items-center gap-2 rounded-xl border border-cyan-300/30 bg-cyan-400/10 px-3 py-2 text-xs font-medium text-cyan-200 transition hover:bg-cyan-400/20"
          >
            <Smartphone className="h-4 w-4" />
            Portal Preview
          </button>
          <button
            onClick={() => fetchData()}
            className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs font-medium text-zinc-300 hover:bg-white/10 transition"
          >
            <RefreshCw className="h-3.5 w-3.5" /> Sync
          </button>
        </div>
      </div>

      {/* Operational Tab Strip */}
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
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <MetricCard
              label="Today's Gross Sales"
              value={formatCurrency(dailyGross)}
              icon={<CircleDollarSign className="h-5 w-5" />}
              trend={`${todayTx.length} payments today`}
              trendUp={true}
              accent="emerald"
            />
            <MetricCard
              label="Monthly Net Earnings"
              value={formatCurrency(netEarnings)}
              icon={<Wallet className="h-5 w-5" />}
              trend="After platform fee"
              trendUp={true}
              accent="indigo"
            />
            <MetricCard
              label="Active Subscribers"
              value={String(activeSubscriberCount)}
              icon={<Users className="h-5 w-5" />}
              trend={`${activeSessions.length} currently connected`}
              trendUp={true}
              accent="sky"
            />
            <MetricCard
              label="Online Routers"
              value={`${onlineRouters} / ${routers.length}`}
              icon={<RouterIcon className="h-5 w-5" />}
              trend={`${onlineRouters === routers.length && routers.length > 0 ? 'All nodes online' : 'Infrastructure healthy'}`}
              trendUp={onlineRouters === routers.length}
              accent="amber"
            />
          </div>

          {/* Traffic Throughput & Health Meters */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <div className="glass-card rounded-2xl p-5 lg:col-span-2">
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-semibold text-white">Live Real-Time Traffic (TX / RX)</h3>
                  <p className="text-xs text-zinc-500">Live throughput stream from MikroTik routers</p>
                </div>
                <div className="flex items-center gap-3 text-xs">
                  <span className="flex items-center gap-1.5 text-cyan-300">
                    <span className="h-2 w-2 rounded-full bg-cyan-400" /> Upload (TX)
                  </span>
                  <span className="flex items-center gap-1.5 text-indigo-400">
                    <span className="h-2 w-2 rounded-full bg-indigo-500" /> Download (RX)
                  </span>
                </div>
              </div>
              <ResponsiveContainer width="100%" height={240}>
                <AreaChart data={chartData}>
                  <defs>
                    <linearGradient id="txGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.4} />
                      <stop offset="95%" stopColor="#06b6d4" stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="rxGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#6366f1" stopOpacity={0.4} />
                      <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                  <XAxis dataKey="time" tick={{ fill: '#71717a', fontSize: 11 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill: '#71717a', fontSize: 11 }} axisLine={false} tickLine={false} />
                  <Tooltip
                    contentStyle={{ background: '#0b2024', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '12px', fontSize: '12px' }}
                    labelStyle={{ color: '#a1a1aa' }}
                    formatter={(v: number) => `${formatSpeed(v)}`}
                  />
                  <Area type="monotone" dataKey="tx" stroke="#06b6d4" strokeWidth={2} fill="url(#txGrad)" />
                  <Area type="monotone" dataKey="rx" stroke="#6366f1" strokeWidth={2} fill="url(#rxGrad)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>

            {/* Health Meters */}
            <div className="glass-card rounded-2xl p-5 space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-white">System & Hardware Health</h3>
                <Zap className="h-4 w-4 text-amber-400" />
              </div>
              <div className="space-y-3 pt-2">
                <div>
                  <div className="flex justify-between text-xs text-zinc-400 mb-1">
                    <span>MikroTik Router CPU</span>
                    <span className="font-semibold text-white">{telemetryData?.health?.mikrotik_cpu ?? 18}%</span>
                  </div>
                  <div className="h-2 rounded-full bg-white/10 overflow-hidden">
                    <div className="h-full bg-cyan-400 rounded-full" style={{ width: `${telemetryData?.health?.mikrotik_cpu ?? 18}%` }} />
                  </div>
                </div>
                <div>
                  <div className="flex justify-between text-xs text-zinc-400 mb-1">
                    <span>Router Memory Usage</span>
                    <span className="font-semibold text-white">{telemetryData?.health?.router_memory ?? 34}%</span>
                  </div>
                  <div className="h-2 rounded-full bg-white/10 overflow-hidden">
                    <div className="h-full bg-indigo-500 rounded-full" style={{ width: `${telemetryData?.health?.router_memory ?? 34}%` }} />
                  </div>
                </div>
                <div>
                  <div className="flex justify-between text-xs text-zinc-400 mb-1">
                    <span>Server RADIUS Latency</span>
                    <span className="font-semibold text-emerald-400">12 ms</span>
                  </div>
                  <div className="h-2 rounded-full bg-white/10 overflow-hidden">
                    <div className="h-full bg-emerald-400 rounded-full" style={{ width: '22%' }} />
                  </div>
                </div>
              </div>

              <div className="pt-4 border-t border-white/10">
                <p className="text-xs text-zinc-400 mb-2 font-semibold">Active Venue Gateways</p>
                <div className="space-y-2">
                  {routers.slice(0, 3).map((r) => (
                    <button
                      key={r.id}
                      type="button"
                      onClick={() => openRouterMetrics(r)}
                      className="flex w-full items-center justify-between rounded-xl bg-white/[0.03] p-2.5 text-left text-xs hover:bg-white/[0.08] focus:outline-none focus:ring-1 focus:ring-cyan-400"
                      aria-label={`View live metrics for ${r.nasname}`}
                    >
                      <div className="flex items-center gap-2">
                        <RouterIcon className="h-3.5 w-3.5 text-cyan-400" />
                        <span className="font-medium text-white">{r.nasname}</span>
                      </div>
                      <StatusBadge status={r.is_online ? 'online' : 'offline'} />
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 2. CUSTOMERS (SUBSCRIBER MANAGEMENT) */}
      {/* ========================================================================= */}
      {activeTab === 'customers' && (
        <div className="glass-card rounded-2xl overflow-hidden">
          <div className="flex flex-col gap-3 border-b border-white/10 px-6 py-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h3 className="text-base font-bold text-white">Subscriber Directory (Hotspot & PPPoE)</h3>
              <p className="text-xs text-zinc-400">Manage client profiles, credentials, service tiers, and subscriptions</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-zinc-500" />
                <input
                  type="text"
                  placeholder="Search name, phone, MAC..."
                  value={customerSearch}
                  onChange={(e) => setCustomerSearch(e.target.value)}
                  className="rounded-xl border border-white/10 bg-white/5 pl-8 pr-3 py-1.5 text-xs text-white placeholder-zinc-500 outline-none focus:border-cyan-400"
                />
              </div>
              <div className="flex rounded-xl border border-white/10 p-0.5 bg-white/5">
                {(['all', 'hotspot', 'pppoe'] as const).map((t) => (
                  <button
                    key={t}
                    onClick={() => setCustomerTypeFilter(t)}
                    className={`rounded-lg px-2.5 py-1 text-xs font-semibold capitalize transition ${
                      customerTypeFilter === t ? 'bg-cyan-400 text-[#071014]' : 'text-zinc-400 hover:text-white'
                    }`}
                  >
                    {t}
                  </button>
                ))}
              </div>
              <button
                onClick={() => setShowCustomerModal(true)}
                className="flex items-center gap-1.5 rounded-xl bg-cyan-400 px-3 py-1.5 text-xs font-semibold text-[#071014] hover:bg-cyan-300 transition"
              >
                <Plus className="h-3.5 w-3.5" /> Add Customer
              </button>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-white/10 bg-white/[0.02] text-xs font-medium text-zinc-400">
                <tr>
                  <th className="px-6 py-3.5">Subscriber</th>
                  <th className="px-6 py-3.5">Service Type</th>
                  <th className="px-6 py-3.5">Plan Name</th>
                  <th className="px-6 py-3.5">MAC / Assigned IP</th>
                  <th className="px-6 py-3.5">Data Consumed</th>
                  <th className="px-6 py-3.5">Status</th>
                  <th className="px-6 py-3.5">Expires</th>
                  <th className="px-6 py-3.5 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {customers
                  .filter((c) => {
                    const matchType = customerTypeFilter === 'all' || c.service_type === customerTypeFilter;
                    const matchSearch =
                      !customerSearch ||
                      c.name.toLowerCase().includes(customerSearch.toLowerCase()) ||
                      c.phone_number.includes(customerSearch) ||
                      c.mac_address.toLowerCase().includes(customerSearch.toLowerCase());
                    return matchType && matchSearch;
                  })
                  .map((customer) => (
                    <tr key={customer.id} className="hover:bg-white/[0.02] transition">
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-3">
                          <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-cyan-400/10 text-cyan-300 font-bold text-xs border border-cyan-400/20">
                            {customer.name.charAt(0).toUpperCase()}
                          </div>
                          <div>
                            <p className="font-semibold text-white">{customer.name}</p>
                            <p className="text-xs text-zinc-500 font-mono">{customer.phone_number}</p>
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <span
                          className={`rounded-lg px-2.5 py-1 text-xs font-bold uppercase tracking-wider ${
                            customer.service_type === 'pppoe'
                              ? 'bg-purple-500/10 text-purple-300 border border-purple-500/20'
                              : 'bg-cyan-500/10 text-cyan-300 border border-cyan-500/20'
                          }`}
                        >
                          {customer.service_type}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-xs font-medium text-zinc-300">
                        {customer.plan_name}
                      </td>
                      <td className="px-6 py-4 font-mono text-xs text-zinc-400">
                        <p className="text-white">{customer.ip_address}</p>
                        <p className="text-[11px] text-zinc-500">{customer.mac_address}</p>
                      </td>
                      <td className="px-6 py-4 text-xs">
                        <span className="font-semibold text-cyan-300">{formatBytes(customer.download_bytes)}</span>
                        <span className="text-zinc-500 text-[11px]"> down</span>
                      </td>
                      <td className="px-6 py-4">
                        <StatusBadge
                          status={
                            customer.expires_at && new Date(customer.expires_at).getTime() <= Date.now()
                              ? 'expired'
                              : customer.status
                          }
                        />
                      </td>
                      <td className="px-6 py-4 text-xs text-zinc-400">
                        {customer.expires_at ? timeAgo(customer.expires_at) : 'Active'}
                      </td>
                      <td className="px-6 py-4 text-right">
                        <button
                          onClick={() => toast(`Reset credentials for ${customer.name}`)}
                          className="rounded-lg border border-white/10 px-2 py-1 text-xs text-zinc-300 hover:bg-white/10 transition"
                        >
                          Reset
                        </button>
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 3. HOTSPOT & PPPOE SESSIONS, CREDENTIALS, BRANDING */}
      {/* ========================================================================= */}
      {activeTab === 'hotspot_pppoe' && (
        <div className="space-y-6">
          <div className="flex gap-2 border-b border-white/10 pb-3">
            <button
              onClick={() => setHotspotSubTab('sessions')}
              className={`rounded-xl px-3 py-1.5 text-xs font-semibold transition ${
                hotspotSubTab === 'sessions' ? 'bg-cyan-400 text-[#071014]' : 'text-zinc-400 hover:text-white'
              }`}
            >
              Active Hotspot & PPPoE Sessions ({activeSessions.length})
            </button>
            <button
              onClick={() => setHotspotSubTab('pppoe')}
              className={`rounded-xl px-3 py-1.5 text-xs font-semibold transition ${
                hotspotSubTab === 'pppoe' ? 'bg-cyan-400 text-[#071014]' : 'text-zinc-400 hover:text-white'
              }`}
            >
              PPPoE Profiles & Secrets
            </button>
            <button
              onClick={() => setHotspotSubTab('branding')}
              className={`rounded-xl px-3 py-1.5 text-xs font-semibold transition ${
                hotspotSubTab === 'branding' ? 'bg-cyan-400 text-[#071014]' : 'text-zinc-400 hover:text-white'
              }`}
            >
              Captive Portal Settings & Branding
            </button>
          </div>

          {/* Sub-tab 1: Active Sessions */}
          {hotspotSubTab === 'sessions' && (
            <div className="glass-card rounded-2xl overflow-hidden">
              <div className="flex items-center justify-between border-b border-white/10 px-6 py-4">
                <div>
                  <h3 className="text-base font-bold text-white">Live Active Network Sessions</h3>
                  <p className="text-xs text-zinc-400">Real-time MikroTik hotspot and PPPoE client bindings with kick capability</p>
                </div>
                <span className="flex items-center gap-1.5 rounded-full bg-emerald-500/10 px-3 py-1 text-xs font-medium text-emerald-300 border border-emerald-500/20">
                  <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
                  {activeSessions.length} Active Sessions
                </span>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="border-b border-white/10 bg-white/[0.02] text-xs font-medium text-zinc-400">
                    <tr>
                      <th className="px-6 py-3.5">Username / MAC</th>
                      <th className="px-6 py-3.5">Assigned IP</th>
                      <th className="px-6 py-3.5">Service</th>
                      <th className="px-6 py-3.5">Router Node</th>
                      <th className="px-6 py-3.5">Session Uptime</th>
                      <th className="px-6 py-3.5">Downloaded / Uploaded</th>
                      <th className="px-6 py-3.5 text-right">Disconnect Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {activeSessions.map((session) => (
                      <tr key={session.id} className="hover:bg-white/[0.02] transition">
                        <td className="px-6 py-4">
                          <p className="font-semibold text-white">{session.username}</p>
                          <p className="font-mono text-xs text-zinc-400">{session.mac_address}</p>
                        </td>
                        <td className="px-6 py-4 font-mono text-xs text-cyan-300">
                          {session.ip_address}
                        </td>
                        <td className="px-6 py-4">
                          <span
                            className={`rounded-lg px-2.5 py-1 text-[11px] font-bold uppercase tracking-wider ${
                              session.service_type === 'pppoe'
                                ? 'bg-purple-500/10 text-purple-300 border border-purple-500/20'
                                : 'bg-cyan-500/10 text-cyan-300 border border-cyan-500/20'
                            }`}
                          >
                            {session.service_type}
                          </span>
                        </td>
                        <td className="px-6 py-4 text-xs text-zinc-400">
                          {session.router_name}
                        </td>
                        <td className="px-6 py-4 text-xs text-zinc-300">
                          {Math.floor(session.uptime_seconds / 60)} minutes
                        </td>
                        <td className="px-6 py-4 text-xs font-mono">
                          <span className="text-cyan-300 font-semibold">{formatBytes(session.rx_bytes)}</span>
                          <span className="text-zinc-500"> / {formatBytes(session.tx_bytes)}</span>
                        </td>
                        <td className="px-6 py-4 text-right">
                          <button
                            onClick={() => handleKickSession(session.id, session.username)}
                            disabled={disconnectingSessionId !== null}
                            className="ml-auto flex items-center gap-1.5 rounded-lg border border-rose-500/20 bg-rose-500/10 px-2.5 py-1 text-xs font-semibold text-rose-300 transition hover:bg-rose-500/20 disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {disconnectingSessionId === session.id
                              ? <Loader2 className="h-3 w-3 animate-spin" />
                              : <Power className="h-3 w-3" />}
                            {disconnectingSessionId === session.id ? 'Disconnecting...' : 'Disconnect'}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Sub-tab 2: PPPoE Profiles */}
          {hotspotSubTab === 'pppoe' && (
            <div className="glass-card rounded-2xl p-6 space-y-4">
              <div className="flex items-center justify-between border-b border-white/10 pb-4">
                <div>
                  <h3 className="text-base font-bold text-white">PPPoE Server Profiles & Secrets</h3>
                  <p className="text-xs text-zinc-400">Static IP assignments, remote address pools, and broadband credentials</p>
                </div>
                <button
                  onClick={() => {
                    setCustomerForm((prev) => ({ ...prev, service_type: 'pppoe' }));
                    setShowCustomerModal(true);
                  }}
                  className="flex items-center gap-1.5 rounded-xl bg-cyan-400 px-3 py-1.5 text-xs font-semibold text-[#071014] hover:bg-cyan-300 transition"
                >
                  <Plus className="h-3.5 w-3.5" /> Add PPPoE User
                </button>
              </div>

              <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
                  <p className="text-xs font-bold uppercase tracking-wider text-zinc-500">PPPoE Pool Subnet</p>
                  <p className="mt-2 font-mono text-lg text-white">10.20.0.0/24</p>
                  <p className="text-xs text-zinc-500 mt-1">Gateway: 10.20.0.1</p>
                </div>
                <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
                  <p className="text-xs font-bold uppercase tracking-wider text-zinc-500">Active PPPoE Leases</p>
                  <p className="mt-2 font-mono text-lg text-cyan-300">{customers.filter((c) => c.service_type === 'pppoe').length} subscribers</p>
                  <p className="text-xs text-emerald-400 mt-1">RADIUS authenticated</p>
                </div>
                <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
                  <p className="text-xs font-bold uppercase tracking-wider text-zinc-500">Primary DNS</p>
                  <p className="mt-2 font-mono text-lg text-indigo-300">1.1.1.1, 8.8.8.8</p>
                  <p className="text-xs text-zinc-500 mt-1">Cloudflare & Google DNS</p>
                </div>
              </div>
            </div>
          )}

          {/* Sub-tab 3: Captive Portal Settings */}
          {hotspotSubTab === 'branding' && (
            <div className="glass-card rounded-2xl p-6 space-y-6">
              <div className="flex flex-col gap-3 border-b border-white/10 pb-4 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <h3 className="text-base font-bold text-white">Captive Portal Branding & Customization</h3>
                  <p className="text-xs text-zinc-400">Configure subscriber onboarding experience and Wi-Fi login splash screen</p>
                </div>
                <button
                  type="button"
                  onClick={() => setShowMobilePreview((visible) => !visible)}
                  aria-expanded={showMobilePreview}
                  className="flex shrink-0 items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-xs font-semibold text-zinc-200 transition hover:border-cyan-300/40 hover:bg-cyan-300/10 hover:text-white"
                >
                  <Smartphone className="h-4 w-4 text-cyan-300" />
                  {showMobilePreview ? 'Hide Mobile Preview' : 'Preview on Mobile'}
                </button>
              </div>

              <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
                <div className="space-y-4">
                  <div>
                    <label className="text-xs text-zinc-400">Welcome Splash Headline</label>
                    <input
                      type="text"
                      value={branding.welcome_headline}
                      onChange={(e) => setBranding({ ...branding, welcome_headline: e.target.value })}
                      placeholder="e.g. Welcome to High Speed Campus Wi-Fi"
                      className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-zinc-400">Logo Image URL</label>
                    <input
                      type="url"
                      value={branding.logo_url}
                      onChange={(e) => setBranding({ ...branding, logo_url: e.target.value })}
                      placeholder="https://example.com/logo.png"
                      className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-zinc-400">Brand Color Accent</label>
                    <div className="mt-1 flex items-center gap-3">
                      <input
                        type="color"
                        value={branding.brand_color}
                        onChange={(e) => setBranding({ ...branding, brand_color: e.target.value })}
                        className="h-10 w-16 rounded-lg border border-white/10 bg-white/5 p-1 cursor-pointer"
                      />
                      <span className="font-mono text-sm text-white">{branding.brand_color}</span>
                    </div>
                  </div>
                </div>

                <div className="space-y-4">
                  <div>
                    <label className="text-xs text-zinc-400">Terms of Service / Acceptable Use Policy</label>
                    <textarea
                      rows={6}
                      value={branding.terms_of_service}
                      onChange={(e) => setBranding({ ...branding, terms_of_service: e.target.value })}
                      placeholder="Enter legal terms presented to subscribers before internet access is authorized..."
                      className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 p-3 text-xs text-white outline-none focus:border-cyan-400 font-sans"
                    />
                  </div>
                </div>
              </div>

              <div className="flex justify-end border-t border-white/10 pt-4">
                <button
                  onClick={handleSaveBranding}
                  disabled={savingBranding}
                  className="flex items-center gap-2 rounded-xl bg-cyan-400 px-5 py-2.5 text-xs font-semibold text-[#071014] transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {savingBranding && <Loader2 className="h-4 w-4 animate-spin" />}
                  {savingBranding ? 'Saving...' : 'Save Portal Branding'}
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ========================================================================= */}
      {/* 4. PLANS & VOUCHERS */}
      {/* ========================================================================= */}
      {activeTab === 'plans_vouchers' && (
        <div className="space-y-6">
          <div className="flex gap-2 border-b border-white/10 pb-3">
            <button
              onClick={() => setPlansVouchersSubTab('plans')}
              className={`rounded-xl px-3 py-1.5 text-xs font-semibold transition ${
                plansVouchersSubTab === 'plans' ? 'bg-cyan-400 text-[#071014]' : 'text-zinc-400 hover:text-white'
              }`}
            >
              Service Plans ({plans.length})
            </button>
            <button
              onClick={() => setPlansVouchersSubTab('vouchers')}
              className={`rounded-xl px-3 py-1.5 text-xs font-semibold transition ${
                plansVouchersSubTab === 'vouchers' ? 'bg-cyan-400 text-[#071014]' : 'text-zinc-400 hover:text-white'
              }`}
            >
              Prepaid Vouchers ({vouchers.length})
            </button>
          </div>

          {/* Sub-tab 1: Service Plans */}
          {plansVouchersSubTab === 'plans' && (
            <div className="glass-card rounded-2xl overflow-hidden">
              <div className="flex items-center justify-between border-b border-white/10 px-6 py-4">
                <div>
                  <h3 className="text-base font-bold text-white">Vendor Service Plans</h3>
                  <p className="text-xs text-zinc-400">Broadband packages, durations, speeds, and price points</p>
                </div>
                <button
                  onClick={() => setShowPlanModal(true)}
                  className="flex items-center gap-1.5 rounded-xl bg-cyan-400 px-3 py-1.5 text-xs font-semibold text-[#071014] hover:bg-cyan-300 transition"
                >
                  <Plus className="h-3.5 w-3.5" /> Create Plan
                </button>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="border-b border-white/10 bg-white/[0.02] text-xs font-medium text-zinc-400">
                    <tr>
                      <th className="px-6 py-3.5">Plan Name</th>
                      <th className="px-6 py-3.5">Price</th>
                      <th className="px-6 py-3.5">Duration</th>
                      <th className="px-6 py-3.5">Bandwidth (Down / Up)</th>
                      <th className="px-6 py-3.5">Devices</th>
                      <th className="px-6 py-3.5">Status</th>
                      <th className="px-6 py-3.5 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {plans.map((plan) => (
                      <tr key={plan.id} className="hover:bg-white/[0.02] transition">
                        <td className="px-6 py-4 font-semibold text-white">{plan.name}</td>
                        <td className="px-6 py-4 font-bold text-cyan-300">{formatCurrency(Number(plan.price))}</td>
                        <td className="px-6 py-4 text-xs text-zinc-300">{formatDuration(plan.duration_minutes)}</td>
                        <td className="px-6 py-4 font-mono text-xs text-zinc-300">
                          {formatSpeed(plan.download_speed_kbps)} / {formatSpeed(plan.upload_speed_kbps)}
                        </td>
                        <td className="px-6 py-4 text-xs text-zinc-400">
                          {plan.simultaneous_devices} device{plan.simultaneous_devices > 1 ? 's' : ''}
                        </td>
                        <td className="px-6 py-4">
                          <StatusBadge status={plan.is_active ? 'active' : 'suspended'} />
                        </td>
                        <td className="px-6 py-4 text-right">
                          <button
                            onClick={() => handleTogglePlan(plan)}
                            disabled={togglingPlanId !== null}
                            className="inline-flex items-center gap-1 rounded-lg border border-white/10 px-2 py-1 text-xs text-zinc-300 hover:bg-white/10 transition disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {togglingPlanId === plan.id && <Loader2 className="h-3 w-3 animate-spin" />}
                            {togglingPlanId === plan.id ? 'Updating...' : plan.is_active ? 'Deactivate' : 'Activate'}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Sub-tab 2: Prepaid Vouchers */}
          {plansVouchersSubTab === 'vouchers' && (
            <div className="glass-card rounded-2xl overflow-hidden">
              <div className="flex flex-col gap-3 border-b border-white/10 px-6 py-4 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <h3 className="text-base font-bold text-white">Prepaid Access Vouchers</h3>
                  <p className="text-xs text-zinc-400">Generate, batch print, and manage scratch voucher tokens</p>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setShowVoucherModal(true)}
                    className="flex items-center gap-1.5 rounded-xl bg-cyan-400 px-3 py-1.5 text-xs font-semibold text-[#071014] hover:bg-cyan-300 transition"
                  >
                    <Plus className="h-3.5 w-3.5" /> Generate Vouchers
                  </button>
                  <button
                    onClick={() => setShowBatchPrintModal(true)}
                    className="flex items-center gap-1.5 rounded-xl border border-white/10 bg-white/5 px-3 py-1.5 text-xs font-semibold text-white hover:bg-white/10 transition"
                  >
                    <Printer className="h-3.5 w-3.5" /> Batch Print
                  </button>
                  <button
                    onClick={handleDeleteUsedVouchers}
                    disabled={deletingUsedVouchers}
                    className="flex items-center gap-1.5 rounded-xl border border-rose-500/20 bg-rose-500/10 px-3 py-1.5 text-xs font-semibold text-rose-300 transition hover:bg-rose-500/20 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {deletingUsedVouchers
                      ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      : <Trash2 className="h-3.5 w-3.5" />}
                    {deletingUsedVouchers ? 'Clearing...' : 'Clear Used'}
                  </button>
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="border-b border-white/10 bg-white/[0.02] text-xs font-medium text-zinc-400">
                    <tr>
                      <th className="px-6 py-3.5">Voucher Code</th>
                      <th className="px-6 py-3.5">Status</th>
                      <th className="px-6 py-3.5">Assigned MAC</th>
                      <th className="px-6 py-3.5">Generated On</th>
                      <th className="px-6 py-3.5">Expiration</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {vouchers.map((voucher) => (
                      <tr key={voucher.id} className="hover:bg-white/[0.02] transition">
                        <td className="px-6 py-4 font-mono font-bold text-cyan-300 tracking-wider">
                          {voucher.code}
                        </td>
                        <td className="px-6 py-4">
                          <span
                            className={`rounded-full px-2.5 py-0.5 text-[11px] font-bold ${
                              voucher.status === 'USED'
                                ? 'bg-zinc-500/10 text-zinc-400'
                                : 'bg-emerald-400/10 text-emerald-300'
                            }`}
                          >
                            {voucher.status}
                          </span>
                        </td>
                        <td className="px-6 py-4 font-mono text-xs text-zinc-400">
                          {voucher.assigned_mac || '—'}
                        </td>
                        <td className="px-6 py-4 text-xs text-zinc-400">
                          {formatDate(voucher.created_at)}
                        </td>
                        <td className="px-6 py-4 text-xs text-zinc-500">
                          {voucher.expires_at ? formatDate(voucher.expires_at) : '30 days'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ========================================================================= */}
      {/* 5. SUBSCRIPTIONS & PAYSTACK PAYMENTS */}
      {/* ========================================================================= */}
      {activeTab === 'subscriptions_payments' && (
        <div className="space-y-5">
        {canManagePayments && (
          <section className="glass-card rounded-2xl p-6">
            <div className="flex flex-col gap-3 border-b border-white/10 pb-4 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <h3 className="text-base font-bold text-white">Payment Gateway (Paystack M-Pesa)</h3>
                <p className="mt-1 text-xs text-zinc-400">
                  Paystack credentials are encrypted at rest and never returned by the API.
                </p>
              </div>
              <span className={`w-fit rounded-full px-3 py-1 text-[10px] font-semibold ${paystackSecretKeySet ? 'bg-emerald-400/10 text-emerald-300' : 'bg-amber-400/10 text-amber-300'}`}>
                {paystackSecretKeySet ? 'Gateway configured' : 'Setup required'}
              </span>
            </div>

            <div className="mt-5 grid gap-4 md:grid-cols-2">
              <div>
                <label htmlFor="paystack-billing-email" className="text-xs text-zinc-400">Receipt / settlement email</label>
                <input
                  id="paystack-billing-email"
                  type="email"
                  autoComplete="email"
                  required
                  value={paystackBillingEmail}
                  onChange={(event) => setPaystackBillingEmail(event.target.value)}
                  placeholder="billing@example.com"
                  className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-cyan-400"
                />
              </div>
              <div>
                <label htmlFor="paystack-secret-key" className="text-xs text-zinc-400">Paystack Secret Key</label>
                <input
                  id="paystack-secret-key"
                  type="password"
                  autoComplete="new-password"
                  required={!paystackSecretKeySet}
                  value={paystackSecretKey}
                  onChange={(event) => setPaystackSecretKey(event.target.value)}
                  placeholder={paystackSecretKeySet ? 'Saved — leave blank to keep current' : 'sk_test_… or sk_live_…'}
                  className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-cyan-400"
                />
              </div>
            </div>
            <div className="mt-5 flex justify-end border-t border-white/10 pt-4">
              <button
                type="button"
                onClick={handleSavePaystackConfiguration}
                disabled={savingPaystackConfiguration}
                className="flex items-center gap-2 rounded-xl bg-cyan-400 px-5 py-2.5 text-xs font-semibold text-[#071014] transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {savingPaystackConfiguration && <Loader2 className="h-4 w-4 animate-spin" />}
                {savingPaystackConfiguration ? 'Saving securely…' : 'Save Paystack Settings'}
              </button>
            </div>
          </section>
        )}

        <div className="glass-card rounded-2xl overflow-hidden">
          <div className="flex flex-col gap-3 border-b border-white/10 px-6 py-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h3 className="text-base font-bold text-white">Subscriptions & M-Pesa Collections</h3>
              <p className="text-xs text-zinc-400">Paystack mobile money requests, checkout receipts, and customer renewals</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-zinc-500" />
                <input
                  type="text"
                  placeholder="Search receipt or phone..."
                  value={txSearch}
                  onChange={(e) => setTxSearch(e.target.value)}
                  className="rounded-xl border border-white/10 bg-white/5 pl-8 pr-3 py-1.5 text-xs text-white placeholder-zinc-500 outline-none focus:border-cyan-400"
                />
              </div>
              <select
                value={txStatusFilter}
                onChange={(e) => setTxStatusFilter(e.target.value)}
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
                  <th className="px-6 py-3.5">Payment Ref</th>
                  <th className="px-6 py-3.5">Subscriber Phone</th>
                  <th className="px-6 py-3.5">Gross Amount</th>
                  <th className="px-6 py-3.5">Platform Fee</th>
                  <th className="px-6 py-3.5">Gateway Fee</th>
                  <th className="px-6 py-3.5">Net Vendor Credit</th>
                  <th className="px-6 py-3.5">Status</th>
                  <th className="px-6 py-3.5">Date & Time</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {transactions
                  .filter((tx) => {
                    const matchStatus = txStatusFilter === 'all' || (tx.status || '').toLowerCase() === txStatusFilter.toLowerCase();
                    const matchSearch =
                      !txSearch ||
                      (tx.customer_phone || '').includes(txSearch) ||
                      (tx.payment_ref || '').toLowerCase().includes(txSearch.toLowerCase());
                    return matchStatus && matchSearch;
                  })
                  .map((tx) => (
                    <tr key={tx.id} className="hover:bg-white/[0.02] transition">
                      <td className="px-6 py-4 font-mono text-xs">
                        <div className="font-bold text-cyan-300">
                          {tx.payment_ref || tx.id.slice(0, 10)}
                        </div>
                        {tx.gateway_receipt && (
                          <div className="mt-1 text-[10px] text-zinc-500">
                            Receipt: {tx.gateway_receipt}
                          </div>
                        )}
                      </td>
                      <td className="px-6 py-4 font-mono text-xs text-white">
                        {tx.customer_phone}
                      </td>
                      <td className="px-6 py-4 font-bold text-white">
                        {formatCurrency(Number(tx.gross_amount))}
                      </td>
                      <td className="px-6 py-4 text-xs text-emerald-400">
                        {formatCurrency(Number(tx.platform_fee))}
                      </td>
                      <td className="px-6 py-4 text-xs text-zinc-400">
                        {formatCurrency(Number(tx.gateway_fee || 0))}
                      </td>
                      <td className="px-6 py-4 font-semibold text-indigo-300 text-xs">
                        {formatCurrency(Number(tx.vendor_net_amount))}
                      </td>
                      <td className="px-6 py-4">
                        <StatusBadge status={tx.status} />
                      </td>
                      <td className="px-6 py-4 text-xs text-zinc-500">
                        {formatDateTime(tx.paid_at || tx.created_at)}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 6. INVOICES & ROUTER BINDINGS */}
      {/* ========================================================================= */}
      {activeTab === 'invoices_routers' && (
        <div className="space-y-6">
          <div className="flex gap-2 border-b border-white/10 pb-3">
            <button
              onClick={() => setInvoicesRoutersSubTab('invoices')}
              className={`rounded-xl px-3 py-1.5 text-xs font-semibold transition ${
                invoicesRoutersSubTab === 'invoices' ? 'bg-cyan-400 text-[#071014]' : 'text-zinc-400 hover:text-white'
              }`}
            >
              Billing Invoices ({invoices.length})
            </button>
            <button
              onClick={() => setInvoicesRoutersSubTab('routers')}
              className={`rounded-xl px-3 py-1.5 text-xs font-semibold transition ${
                invoicesRoutersSubTab === 'routers' ? 'bg-cyan-400 text-[#071014]' : 'text-zinc-400 hover:text-white'
              }`}
            >
              Router Bindings & Provisioning ({routers.length})
            </button>
          </div>

          {/* Sub-tab 1: Invoices */}
          {invoicesRoutersSubTab === 'invoices' && (
            <div className="glass-card rounded-2xl overflow-hidden">
              <div className="flex items-center justify-between border-b border-white/10 px-6 py-4">
                <div>
                  <h3 className="text-base font-bold text-white">Automated Customer Invoices</h3>
                  <p className="text-xs text-zinc-400">Billing records, payment receipts, and recurring invoices</p>
                </div>
                <button
                  onClick={() => setShowInvoiceModal(true)}
                  className="flex items-center gap-1.5 rounded-xl bg-cyan-400 px-3 py-1.5 text-xs font-semibold text-[#071014] hover:bg-cyan-300 transition"
                >
                  <Plus className="h-3.5 w-3.5" /> Create Invoice
                </button>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="border-b border-white/10 bg-white/[0.02] text-xs font-medium text-zinc-400">
                    <tr>
                      <th className="px-6 py-3.5">Invoice #</th>
                      <th className="px-6 py-3.5">Subscriber</th>
                      <th className="px-6 py-3.5">Service Plan</th>
                      <th className="px-6 py-3.5">Amount</th>
                      <th className="px-6 py-3.5">Issued Date</th>
                      <th className="px-6 py-3.5">Due Date</th>
                      <th className="px-6 py-3.5">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {invoices.map((inv) => (
                      <tr key={inv.id} className="hover:bg-white/[0.02] transition">
                        <td className="px-6 py-4 font-mono font-bold text-cyan-300 text-xs">
                          {inv.invoice_number}
                        </td>
                        <td className="px-6 py-4">
                          <p className="font-semibold text-white">{inv.customer_name}</p>
                          <p className="font-mono text-xs text-zinc-500">{inv.customer_phone}</p>
                        </td>
                        <td className="px-6 py-4 text-xs text-zinc-300">
                          {inv.plan_name}
                        </td>
                        <td className="px-6 py-4 font-bold text-white">
                          {formatCurrency(Number(inv.amount))}
                        </td>
                        <td className="px-6 py-4 text-xs text-zinc-400">
                          {formatDate(inv.date)}
                        </td>
                        <td className="px-6 py-4 text-xs text-zinc-400">
                          {formatDate(inv.due_date)}
                        </td>
                        <td className="px-6 py-4">
                          <StatusBadge status={inv.status} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Sub-tab 2: Routers */}
          {invoicesRoutersSubTab === 'routers' && (
            <div className="glass-card rounded-2xl overflow-hidden">
              <div className="flex items-center justify-between border-b border-white/10 px-6 py-4">
                <div>
                  <h3 className="text-base font-bold text-white">Vendor Router Hardware Bindings</h3>
                  <p className="text-xs text-zinc-400">Bind your physical MikroTik hardware with NetPulse RADIUS & API</p>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => void fetchRouters()}
                    disabled={routerLoading}
                    className="flex items-center gap-1.5 rounded-xl border border-white/10 px-3 py-1.5 text-xs font-semibold text-zinc-200 hover:bg-white/10 transition disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <RefreshCw className={`h-3.5 w-3.5 ${routerLoading ? 'animate-spin' : ''}`} />
                    {routerLoading ? 'Refreshing…' : 'Refresh Routers'}
                  </button>
                  <button
                    onClick={openCreateRouter}
                    className="flex items-center gap-1.5 rounded-xl bg-cyan-400 px-3 py-1.5 text-xs font-semibold text-[#071014] hover:bg-cyan-300 transition"
                  >
                    <Plus className="h-3.5 w-3.5" /> Bind Router
                  </button>
                </div>
              </div>

              {routerError && (
                <div className="border-b border-amber-400/20 bg-amber-400/5 px-6 py-3 text-xs text-amber-200">
                  Router list could not be refreshed: {routerError}
                </div>
              )}

              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="border-b border-white/10 bg-white/[0.02] text-xs font-medium text-zinc-400">
                    <tr>
                      <th className="px-6 py-3.5">Router Identifier</th>
                      <th className="px-6 py-3.5">Management IP</th>
                      <th className="px-6 py-3.5">Health Status</th>
                      <th className="px-6 py-3.5">Last Check-in</th>
                      <th className="px-6 py-3.5 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {routerLoading && routers.length === 0 ? (
                      <tr><td colSpan={5} className="px-6 py-10 text-center text-sm text-zinc-400">Loading routers…</td></tr>
                    ) : routerError && routers.length === 0 ? (
                      <tr><td colSpan={5} className="px-6 py-10 text-center text-sm text-zinc-400">Unable to load routers. Use Refresh Routers to try again.</td></tr>
                    ) : routers.length === 0 ? (
                      <tr><td colSpan={5} className="px-6 py-10 text-center text-sm text-zinc-400">No routers connected. Bind a router or refresh to sync connected devices.</td></tr>
                    ) : routers.map((router) => (
                      <tr
                        key={router.id}
                        onClick={() => openRouterMetrics(router)}
                        onKeyDown={(event) => {
                          if (event.key === 'Enter' || event.key === ' ') {
                            event.preventDefault();
                            openRouterMetrics(router);
                          }
                        }}
                        tabIndex={0}
                        role="button"
                        aria-label={`View live metrics for ${router.nasname}`}
                        className="cursor-pointer hover:bg-white/[0.05] focus:outline-none focus:bg-white/[0.05] transition"
                      >
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
                        <td className="px-6 py-4 font-mono text-xs text-zinc-300">
                          {router.nas_ip || '10.10.0.10'}
                        </td>
                        <td className="px-6 py-4">
                          <StatusBadge status={router.is_online ? 'online' : 'offline'} />
                        </td>
                        <td className="px-6 py-4 text-xs text-zinc-500">
                          {router.last_ping ? timeAgo(router.last_ping) : 'Live'}
                        </td>
                        <td className="px-6 py-4 text-right">
                          <div className="flex items-center justify-end gap-2">
                            <button
                              onClick={(event) => {
                                event.stopPropagation();
                                openEditRouter(router);
                              }}
                              aria-label={`Edit ${router.nasname}`}
                              className="rounded-lg border border-white/10 px-2.5 py-1 text-xs text-zinc-300 hover:bg-white/10 transition"
                            >
                              <Pencil className="h-3.5 w-3.5" />
                            </button>
                            <button
                              onClick={(event) => {
                                event.stopPropagation();
                                void handleDeleteRouter(router);
                              }}
                              disabled={deletingRouterId === router.id}
                              aria-label={`Delete ${router.nasname}`}
                              className="rounded-lg border border-red-400/20 px-2.5 py-1 text-xs text-red-300 hover:bg-red-400/10 transition disabled:cursor-not-allowed disabled:opacity-50"
                            >
                              {deletingRouterId === router.id
                                ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                : <Trash2 className="h-3.5 w-3.5" />}
                            </button>
                            <button
                              onClick={(event) => {
                                event.stopPropagation();
                                setSelectedRouterForProvision(router);
                                setShowProvisionModal(true);
                              }}
                              className="rounded-lg bg-cyan-400/10 px-2.5 py-1 text-xs font-semibold text-cyan-300 border border-cyan-400/20 hover:bg-cyan-400/20 transition"
                            >
                              Auto-Provision
                            </button>
                            <button
                              onClick={(event) => {
                                event.stopPropagation();
                                handleViewScript(router);
                              }}
                              className="rounded-lg border border-white/10 px-2.5 py-1 text-xs text-zinc-300 hover:bg-white/10 transition"
                            >
                              Script
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
        </div>
      )}

      {/* ========================================================================= */}
      {/* 7. TICKETS & OPERATIONAL REPORTS */}
      {/* ========================================================================= */}
      {activeTab === 'tickets_reports' && (
        <div className="space-y-6">
          <div className="flex gap-2 border-b border-white/10 pb-3">
            <button
              onClick={() => setTicketsReportsSubTab('tickets')}
              className={`rounded-xl px-3 py-1.5 text-xs font-semibold transition ${
                ticketsReportsSubTab === 'tickets' ? 'bg-cyan-400 text-[#071014]' : 'text-zinc-400 hover:text-white'
              }`}
            >
              Support Tickets ({tickets.length})
            </button>
            <button
              onClick={() => setTicketsReportsSubTab('reports')}
              className={`rounded-xl px-3 py-1.5 text-xs font-semibold transition ${
                ticketsReportsSubTab === 'reports' ? 'bg-cyan-400 text-[#071014]' : 'text-zinc-400 hover:text-white'
              }`}
            >
              Operational Sales Reports
            </button>
          </div>

          {/* Sub-tab 1: Tickets */}
          {ticketsReportsSubTab === 'tickets' && (
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
              <div className="glass-card rounded-2xl overflow-hidden lg:col-span-2">
                <div className="flex items-center justify-between border-b border-white/10 px-6 py-4">
                  <div>
                    <h3 className="text-base font-bold text-white">Subscriber Support Tickets</h3>
                    <p className="text-xs text-zinc-400">Respond to customer issues, connectivity tickets, and billing queries</p>
                  </div>
                  <button
                    onClick={() => setShowTicketModal(true)}
                    className="flex items-center gap-1.5 rounded-xl bg-cyan-400 px-3 py-1.5 text-xs font-semibold text-[#071014] hover:bg-cyan-300 transition"
                  >
                    <Plus className="h-3.5 w-3.5" /> Open Ticket
                  </button>
                </div>

                <div className="divide-y divide-white/5">
                  {tickets.map((ticket) => (
                    <div
                      key={ticket.id}
                      onClick={() => setActiveTicket(ticket)}
                      className={`p-4 cursor-pointer transition hover:bg-white/[0.03] ${
                        activeTicket?.id === ticket.id ? 'bg-white/[0.04] border-l-2 border-cyan-400' : ''
                      }`}
                    >
                      <div className="flex items-start justify-between">
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-xs font-bold text-cyan-300">{ticket.ticket_number}</span>
                            <span
                              className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
                                ticket.priority === 'URGENT' || ticket.priority === 'HIGH'
                                  ? 'bg-rose-500/10 text-rose-300'
                                  : 'bg-amber-500/10 text-amber-300'
                              }`}
                            >
                              {ticket.priority}
                            </span>
                            <span className="text-xs font-semibold text-white">{ticket.subject}</span>
                          </div>
                          <p className="mt-1 text-xs text-zinc-400 line-clamp-1">{ticket.description}</p>
                          <p className="mt-1 text-[11px] text-zinc-500">
                            Subscriber: {ticket.customer_name} ({ticket.customer_phone}) · {timeAgo(ticket.created_at)}
                          </p>
                        </div>
                        <StatusBadge status={ticket.status} />
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Ticket Chat Drawer */}
              <div className="glass-card rounded-2xl p-5 flex flex-col h-[520px]">
                {activeTicket ? (
                  <>
                    <div className="border-b border-white/10 pb-3">
                      <div className="flex justify-between items-center">
                        <span className="font-mono font-bold text-cyan-300 text-xs">{activeTicket.ticket_number}</span>
                        <StatusBadge status={activeTicket.status} />
                      </div>
                      <h4 className="font-semibold text-white text-sm mt-1">{activeTicket.subject}</h4>
                      <p className="text-xs text-zinc-400">{activeTicket.customer_name}</p>
                    </div>

                    <div className="flex-1 overflow-y-auto py-3 space-y-3">
                      {activeTicket.messages?.map((msg) => (
                        <div
                          key={msg.id}
                          className={`rounded-xl p-3 text-xs max-w-[85%] ${
                            msg.is_staff
                              ? 'bg-cyan-400/10 text-cyan-200 border border-cyan-400/20 ml-auto'
                              : 'bg-white/5 text-zinc-300 border border-white/10 mr-auto'
                          }`}
                        >
                          <p className="font-semibold text-[10px] text-zinc-400 mb-1">{msg.sender}</p>
                          <p className="leading-relaxed">{msg.text}</p>
                          <p className="text-[9px] text-zinc-500 text-right mt-1">{timeAgo(msg.created_at)}</p>
                        </div>
                      ))}
                    </div>

                    <div className="pt-3 border-t border-white/10 flex gap-2">
                      <input
                        type="text"
                        placeholder="Type reply to customer..."
                        value={ticketReplyText}
                        onChange={(e) => setTicketReplyText(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && !sendingTicketReply && handleSendTicketReply()}
                        className="flex-1 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs text-white outline-none focus:border-cyan-400"
                      />
                      <button
                        type="button"
                        onClick={handleSendTicketReply}
                        disabled={sendingTicketReply || !ticketReplyText.trim()}
                        className="rounded-xl bg-cyan-400 p-2 text-[#071014] transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {sendingTicketReply
                          ? <Loader2 className="h-4 w-4 animate-spin" />
                          : <Send className="h-4 w-4" />}
                      </button>
                    </div>
                  </>
                ) : (
                  <div className="flex h-full items-center justify-center text-center p-4">
                    <p className="text-xs text-zinc-500">Select a ticket from the left to view the customer conversation thread</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Sub-tab 2: Operational Reports */}
          {ticketsReportsSubTab === 'reports' && (
            <div className="glass-card rounded-2xl p-6 space-y-6">
              <div className="flex items-center justify-between border-b border-white/10 pb-4">
                <div>
                  <h3 className="text-base font-bold text-white">WISP Operational Sales & Traffic Reports</h3>
                  <p className="text-xs text-zinc-400">Package revenue distribution, peak usage patterns, and transaction summaries</p>
                </div>
                <button
                  onClick={() => {
                    window.print();
                    toast('Printing operational report...');
                  }}
                  className="flex items-center gap-2 rounded-xl bg-cyan-400 px-4 py-2 text-xs font-semibold text-[#071014] hover:bg-cyan-300 transition"
                >
                  <Download className="h-3.5 w-3.5" /> Export Report
                </button>
              </div>

              <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
                  <p className="text-xs font-bold uppercase tracking-wider text-zinc-500">Total Net Collections</p>
                  <p className="mt-2 text-2xl font-bold text-emerald-400">{formatCurrency(netEarnings)}</p>
                </div>
                <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
                  <p className="text-xs font-bold uppercase tracking-wider text-zinc-500">Total Transactions</p>
                  <p className="mt-2 text-2xl font-bold text-white">{transactions.length}</p>
                </div>
                <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
                  <p className="text-xs font-bold uppercase tracking-wider text-zinc-500">Active Subscribers</p>
                  <p className="mt-2 text-2xl font-bold text-cyan-300">{customers.length}</p>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ========================================================================= */}
      {/* MODALS */}
      {/* ========================================================================= */}

      {/* Add Customer Modal */}
      <Modal
        open={showCustomerModal}
        onClose={() => setShowCustomerModal(false)}
        title="Add Subscriber (Hotspot / PPPoE)"
        description="Provision a customer with credentials, service type, and rate profile."
      >
        <div className="space-y-4">
          <div>
            <label className="text-xs text-zinc-400">Full Name / Business Name</label>
            <input
              type="text"
              placeholder="e.g. Samuel Mutua"
              value={customerForm.name}
              onChange={(e) => setCustomerForm({ ...customerForm, name: e.target.value })}
              className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
            />
          </div>
          <div>
            <label className="text-xs text-zinc-400">Phone Number (M-Pesa STK)</label>
            <input
              type="tel"
              placeholder="e.g. 254712345678"
              value={customerForm.phone_number}
              onChange={(e) => setCustomerForm({ ...customerForm, phone_number: e.target.value })}
              className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-zinc-400">Service Type</label>
              <select
                value={customerForm.service_type}
                onChange={(e) => setCustomerForm({ ...customerForm, service_type: e.target.value as 'hotspot' | 'pppoe' })}
                className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
              >
                <option value="hotspot" className="bg-zinc-900">Hotspot (Captive Portal)</option>
                <option value="pppoe" className="bg-zinc-900">PPPoE (Home / Biz Fiber)</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-zinc-400">Assigned Plan</label>
              <select
                value={customerForm.plan_name}
                onChange={(e) => setCustomerForm({ ...customerForm, plan_name: e.target.value })}
                className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
              >
                <option value="" className="bg-zinc-900">Select Plan</option>
                {plans.map((p) => (
                  <option key={p.id} value={p.name} className="bg-zinc-900">{p.name} ({formatCurrency(Number(p.price))})</option>
                ))}
              </select>
            </div>
          </div>
          {customerForm.service_type === 'pppoe' && (
            <div>
              <label className="text-xs text-zinc-400">PPPoE Secret / Password</label>
              <input
                type="password"
                autoComplete="new-password"
                placeholder="Enter PPPoE connection password"
                value={customerForm.pppoe_password}
                onChange={(e) => setCustomerForm({ ...customerForm, pppoe_password: e.target.value })}
                className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
              />
            </div>
          )}
          <div>
            <label className="text-xs text-zinc-400">Customer Portal Password</label>
            <input
              type="password"
              autoComplete="new-password"
              minLength={8}
              placeholder="At least 8 characters"
              value={customerForm.portal_password}
              onChange={(e) => setCustomerForm({ ...customerForm, portal_password: e.target.value })}
              className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
            />
          </div>
          <button
            onClick={handleCreateCustomer}
            disabled={creatingCustomer}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-cyan-400 py-2.5 text-xs font-semibold text-[#071014] transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {creatingCustomer && <Loader2 className="h-4 w-4 animate-spin" />}
            {creatingCustomer ? 'Creating...' : 'Create Subscriber'}
          </button>
        </div>
      </Modal>

      {/* Generate Vouchers Modal */}
      <Modal
        open={showVoucherModal}
        onClose={() => setShowVoucherModal(false)}
        title="Generate Prepaid Wi-Fi Vouchers"
        description="Create a batch of random cryptographic tokens for walk-in clients."
        size="sm"
      >
        <div className="space-y-4">
          <div>
            <label className="text-xs text-zinc-400">Batch Quantity (1 - 500)</label>
            <input
              type="number"
              min="1"
              max="500"
              value={voucherForm.count}
              onChange={(e) => setVoucherForm({ ...voucherForm, count: e.target.value })}
              className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
            />
          </div>
          <div>
            <label className="text-xs text-zinc-400">Validity (Days)</label>
            <input
              type="number"
              min="1"
              max="365"
              value={voucherForm.valid_days}
              onChange={(e) => setVoucherForm({ ...voucherForm, valid_days: e.target.value })}
              className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
            />
          </div>
          <button
            onClick={handleGenerateVouchers}
            disabled={generatingVouchers}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-cyan-400 py-2.5 text-xs font-semibold text-[#071014] transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {generatingVouchers && <Loader2 className="h-4 w-4 animate-spin" />}
            {generatingVouchers ? 'Generating...' : 'Generate Batch'}
          </button>
        </div>
      </Modal>

      {/* Batch Print Modal */}
      <Modal
        open={showBatchPrintModal}
        onClose={() => setShowBatchPrintModal(false)}
        title="Printable Voucher Cards"
        description="Rendered grid ready for thermal receipt or paper printout."
        size="lg"
      >
        <div className="space-y-4">
          <div className="max-h-[60vh] overflow-y-auto grid grid-cols-2 sm:grid-cols-3 gap-3 p-2 bg-white rounded-xl text-black">
            {vouchers.slice(0, 18).map((v) => (
              <div key={v.id} className="border border-dashed border-zinc-400 rounded-lg p-3 text-center bg-zinc-50">
                <p className="font-bold text-xs uppercase tracking-wider text-zinc-800">{tenant.business_name}</p>
                <p className="text-[10px] text-zinc-500">Wi-Fi Voucher</p>
                <div className="my-2 rounded bg-zinc-200 py-1.5 font-mono font-bold text-sm tracking-widest text-black">
                  {v.code}
                </div>
                <p className="text-[9px] text-zinc-600">Connect to Wi-Fi & Enter Code</p>
              </div>
            ))}
          </div>
          <button
            onClick={() => {
              window.print();
              toast('Sending vouchers to printer...');
            }}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-cyan-400 py-2.5 text-xs font-semibold text-[#071014] hover:bg-cyan-300 transition"
          >
            <Printer className="h-4 w-4" /> Print Vouchers Now
          </button>
        </div>
      </Modal>

      {/* Create Plan Modal */}
      <Modal
        open={showPlanModal}
        onClose={() => setShowPlanModal(false)}
        title="Create Service Plan"
        description="Configure bandwidth rates and pricing for hotspot or broadband subscribers."
      >
        <div className="space-y-4">
          <div>
            <label className="text-xs text-zinc-400">Plan Name</label>
            <input
              type="text"
              placeholder="e.g. 12-Hour Unlimited High Speed"
              value={planForm.name}
              onChange={(e) => setPlanForm({ ...planForm, name: e.target.value })}
              className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-zinc-400">Price (KES)</label>
              <input
                type="number"
                value={planForm.price}
                onChange={(e) => setPlanForm({ ...planForm, price: e.target.value })}
                className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
              />
            </div>
            <div>
              <label className="text-xs text-zinc-400">Duration</label>
              <div className="mt-1 flex gap-2">
                <input
                  type="number"
                  min="1"
                  value={planForm.duration_value}
                  onChange={(e) => setPlanForm({ ...planForm, duration_value: e.target.value })}
                  className="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
                />
                <select
                  value={planForm.duration_unit}
                  onChange={(e) => setPlanForm({ ...planForm, duration_unit: e.target.value as 'minutes' | 'hours' | 'days' })}
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
                value={planForm.download_speed_kbps}
                onChange={(e) => setPlanForm({ ...planForm, download_speed_kbps: e.target.value })}
                className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
              />
            </div>
            <div>
              <label className="text-xs text-zinc-400">Upload Rate (Kbps)</label>
              <input
                type="number"
                value={planForm.upload_speed_kbps}
                onChange={(e) => setPlanForm({ ...planForm, upload_speed_kbps: e.target.value })}
                className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
              />
            </div>
          </div>
          <button
            onClick={handleCreatePlan}
            disabled={creatingPlan}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-cyan-400 py-2.5 text-xs font-semibold text-[#071014] hover:bg-cyan-300 transition disabled:cursor-not-allowed disabled:opacity-50"
          >
            {creatingPlan && <Loader2 className="h-4 w-4 animate-spin" />}
            {creatingPlan ? 'Creating...' : 'Create Plan'}
          </button>
        </div>
      </Modal>

      {/* Create Invoice Modal */}
      <Modal
        open={showInvoiceModal}
        onClose={() => setShowInvoiceModal(false)}
        title="Generate Customer Billing Invoice"
        description="Issue a formal invoice for broadband or venue Wi-Fi access."
      >
        <div className="space-y-4">
          <div>
            <label className="text-xs text-zinc-400">Customer Name</label>
            <input
              type="text"
              placeholder="e.g. Apex Consult Ltd"
              value={invoiceForm.customer_name}
              onChange={(e) => setInvoiceForm({ ...invoiceForm, customer_name: e.target.value })}
              className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
            />
          </div>
          <div>
            <label className="text-xs text-zinc-400">Customer Phone</label>
            <input
              type="tel"
              placeholder="e.g. 254712345678"
              value={invoiceForm.customer_phone}
              onChange={(e) => setInvoiceForm({ ...invoiceForm, customer_phone: e.target.value })}
              className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-zinc-400">Amount (KES)</label>
              <input
                type="number"
                value={invoiceForm.amount}
                onChange={(e) => setInvoiceForm({ ...invoiceForm, amount: e.target.value })}
                className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
              />
            </div>
            <div>
              <label className="text-xs text-zinc-400">Due In (Days)</label>
              <input
                type="number"
                value={invoiceForm.due_days}
                onChange={(e) => setInvoiceForm({ ...invoiceForm, due_days: e.target.value })}
                className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
              />
            </div>
          </div>
          <button
            onClick={handleCreateInvoice}
            disabled={creatingInvoice}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-cyan-400 py-2.5 text-xs font-semibold text-[#071014] transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {creatingInvoice && <Loader2 className="h-4 w-4 animate-spin" />}
            {creatingInvoice ? 'Creating...' : 'Issue Invoice'}
          </button>
        </div>
      </Modal>

      {/* Open Ticket Modal */}
      <Modal
        open={showTicketModal}
        onClose={() => setShowTicketModal(false)}
        title="Open Support Ticket"
        description="Log an operational issue or subscriber connectivity inquiry."
      >
        <div className="space-y-4">
          <div>
            <label className="text-xs text-zinc-400">Subscriber Name</label>
            <input
              type="text"
              placeholder="e.g. Kevin Mwangi"
              value={ticketForm.customer_name}
              onChange={(e) => setTicketForm({ ...ticketForm, customer_name: e.target.value })}
              className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
            />
          </div>
          <div>
            <label className="text-xs text-zinc-400">Subscriber Phone</label>
            <input
              type="tel"
              placeholder="e.g. 254712345678"
              value={ticketForm.customer_phone}
              onChange={(e) => setTicketForm({ ...ticketForm, customer_phone: e.target.value })}
              className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-zinc-400">Subject</label>
              <input
                type="text"
                placeholder="e.g. Slow speed in Wing B"
                value={ticketForm.subject}
                onChange={(e) => setTicketForm({ ...ticketForm, subject: e.target.value })}
                className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
              />
            </div>
            <div>
              <label className="text-xs text-zinc-400">Priority</label>
              <select
                value={ticketForm.priority}
                onChange={(e) => setTicketForm({ ...ticketForm, priority: e.target.value as SupportTicket['priority'] })}
                className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
              >
                <option value="LOW" className="bg-zinc-900">LOW</option>
                <option value="MEDIUM" className="bg-zinc-900">MEDIUM</option>
                <option value="HIGH" className="bg-zinc-900">HIGH</option>
                <option value="URGENT" className="bg-zinc-900">URGENT</option>
              </select>
            </div>
          </div>
          <div>
            <label className="text-xs text-zinc-400">Issue Details</label>
            <textarea
              rows={3}
              placeholder="Describe symptoms, router node location, error code..."
              value={ticketForm.description}
              onChange={(e) => setTicketForm({ ...ticketForm, description: e.target.value })}
              className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 p-3 text-xs text-white outline-none focus:border-cyan-400 font-sans"
            />
          </div>
          <button
            onClick={handleCreateTicket}
            disabled={creatingTicket}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-cyan-400 py-2.5 text-xs font-semibold text-[#071014] transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {creatingTicket && <Loader2 className="h-4 w-4 animate-spin" />}
            {creatingTicket ? 'Creating...' : 'Create Ticket'}
          </button>
        </div>
      </Modal>

      {/* Bind Router Modal */}
      <Modal
        open={showRouterModal}
        onClose={() => {
          setShowRouterModal(false);
          setEditingRouter(null);
        }}
        title={editingRouter ? 'Edit Network Router' : 'Bind Network Router'}
        description={editingRouter
          ? 'Update router details and credentials. Connectivity is checked separately.'
          : 'Register this MikroTik/CoovaChilli node with the tenant and RADIUS service.'}
      >
        <div className="space-y-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <label className="text-xs text-zinc-400">Router Name / NAS Identity</label>
              <input
                required
                value={newRouter.nasname}
                onChange={(event) => setNewRouter({ ...newRouter, nasname: event.target.value })}
                placeholder="e.g. Westside-Gateway"
                className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
              />
            </div>
            <div>
              <label className="text-xs text-zinc-400">Location Label</label>
              <input
                required
                value={newRouter.shortname}
                onChange={(event) => setNewRouter({ ...newRouter, shortname: event.target.value })}
                placeholder="e.g. Westside"
                className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
              />
            </div>
            <div>
              <label className="text-xs text-zinc-400">Management IP</label>
              <input
                required
                value={newRouter.nas_ip}
                onChange={(event) => setNewRouter({ ...newRouter, nas_ip: event.target.value })}
                placeholder="10.10.0.10"
                className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 font-mono text-sm text-white outline-none focus:border-cyan-400"
              />
            </div>
            <div>
              <label className="text-xs text-zinc-400">RouterOS API Port</label>
              <input
                required
                type="number"
                min="1"
                max="65535"
                value={newRouter.api_port}
                onChange={(event) => setNewRouter({ ...newRouter, api_port: event.target.value })}
                className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 font-mono text-sm text-white outline-none focus:border-cyan-400"
              />
            </div>
            <div>
              <label className="text-xs text-zinc-400">API Username</label>
              <input
                required
                value={newRouter.api_username}
                onChange={(event) => setNewRouter({ ...newRouter, api_username: event.target.value })}
                className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
              />
            </div>
            <div>
              <label className="text-xs text-zinc-400">
                API Password{editingRouter ? ' (leave blank to keep current)' : ''}
              </label>
              <input
                type="password"
                value={newRouter.api_password}
                onChange={(event) => setNewRouter({ ...newRouter, api_password: event.target.value })}
                className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
              />
            </div>
            <div>
              <label className="text-xs text-zinc-400">RADIUS Server IP</label>
              <input
                required
                value={newRouter.radius_server_ip}
                onChange={(event) => setNewRouter({ ...newRouter, radius_server_ip: event.target.value })}
                className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 font-mono text-sm text-white outline-none focus:border-cyan-400"
              />
            </div>
            <div>
              <label className="text-xs text-zinc-400">
                RADIUS Shared Secret{editingRouter ? ' (leave blank to keep current)' : ''}
              </label>
              <input
                required={!editingRouter}
                type="password"
                value={newRouter.shared_secret}
                onChange={(event) => setNewRouter({ ...newRouter, shared_secret: event.target.value })}
                className="mt-1 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400"
              />
            </div>
          </div>
          <button
            onClick={handleSaveRouter}
            disabled={creatingRouter}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-cyan-400 py-2.5 text-xs font-semibold text-[#071014] transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {creatingRouter && <Loader2 className="h-4 w-4 animate-spin" />}
            {creatingRouter
              ? (editingRouter ? 'Saving Router...' : 'Binding Router...')
              : (editingRouter ? 'Save Changes' : 'Bind Router')}
          </button>
        </div>
      </Modal>

      {/* Auto-Provision Router Modal */}
      <Modal
        open={showProvisionModal}
        onClose={() => setShowProvisionModal(false)}
        title="Auto-Provision MikroTik Router"
        description="Verify API credentials and configure RADIUS on this hardware node."
        size="sm"
      >
        <div className="space-y-4">
          <p className="text-xs text-zinc-300">
            Target Host: <span className="font-mono text-cyan-300 font-bold">{selectedRouterForProvision?.nas_ip || '10.10.0.10'}:8728</span>
          </p>
          <p className="text-xs text-zinc-400">
            NetPulse will connect to RouterOS API, install RADIUS AAA configuration, set shared secrets, and verify router health.
          </p>
          <button
            onClick={handleProvisionRouter}
            disabled={provisioningBusy}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-cyan-400 py-2.5 text-xs font-semibold text-[#071014] transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {provisioningBusy && <Loader2 className="h-4 w-4 animate-spin" />}
            {provisioningBusy ? 'Connecting & Provisioning...' : 'Confirm Provisioning'}
          </button>
        </div>
      </Modal>

      {/* Router Script Modal */}
      <Modal
        open={showScriptModal}
        onClose={() => setShowScriptModal(false)}
        title="MikroTik RouterOS Configuration Script"
        description="Copy and paste into your RouterOS terminal to configure RADIUS client."
        size="lg"
      >
        <div className="space-y-4">
          <pre className="max-h-80 overflow-y-auto rounded-xl border border-white/10 bg-black/60 p-4 font-mono text-xs text-cyan-200">
            {activeScript}
          </pre>
          <button
            onClick={() => {
              navigator.clipboard.writeText(activeScript);
              setScriptCopied(true);
              toast('Router config script copied!');
              setTimeout(() => setScriptCopied(false), 2000);
            }}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-cyan-400 py-2.5 text-xs font-semibold text-[#071014] hover:bg-cyan-300 transition"
          >
            {scriptCopied ? <Check className="h-4 w-4" /> : <ExternalLink className="h-4 w-4" />}
            {scriptCopied ? 'Script Copied to Clipboard!' : 'Copy Script to Clipboard'}
          </button>
        </div>
      </Modal>

      <Modal
        open={Boolean(selectedMetricsRouter)}
        onClose={() => setSelectedMetricsRouter(null)}
        title={selectedMetricsRouter ? `${selectedMetricsRouter.nasname} · Live Metrics` : 'Live Router Metrics'}
        description={selectedMetricsRouter?.nas_ip || 'Router management IP unavailable'}
        size="lg"
      >
        <div className="mb-4 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <StatusBadge status={routerMetricsStatus} />
            {routerMetricsStatus === 'connecting' && (
              <span className="text-xs text-zinc-500">Checking router connection</span>
            )}
          </div>
          <button
            type="button"
            onClick={refreshRouterMetrics}
            disabled={!selectedMetricsRouter?.is_online || routerMetricsLoading}
            className="flex items-center gap-2 rounded-lg border border-white/10 px-3 py-1.5 text-xs text-zinc-200 transition hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${routerMetricsLoading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
        {routerMetricsError && (
          <div className="mb-4 rounded-xl border border-rose-400/20 bg-rose-400/10 px-4 py-3 text-sm text-rose-300">
            {routerMetricsError}
          </div>
        )}
        {routerMetricsLoading && !routerMetrics && (
          <div className="flex items-center justify-center gap-2 py-12 text-sm text-zinc-400">
            <RefreshCw className="h-4 w-4 animate-spin" />
            Connecting to router and loading live metrics…
          </div>
        )}
        {!routerMetricsLoading && !routerMetrics && !routerMetricsError && (
          <div className="py-10 text-center text-sm text-zinc-400">Waiting for router metrics…</div>
        )}
        {routerMetrics && (
          <div className="space-y-5">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
                <p className="text-xs text-zinc-400">CPU Usage</p>
                <p className="mt-2 text-2xl font-bold text-white">{routerMetrics.cpu_usage_percent}%</p>
                <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/10">
                  <div
                    className="h-full rounded-full bg-cyan-400"
                    style={{ width: `${Math.min(100, Math.max(0, routerMetrics.cpu_usage_percent))}%` }}
                  />
                </div>
              </div>
              <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
                <p className="text-xs text-zinc-400">Memory Usage</p>
                <p className="mt-2 text-2xl font-bold text-white">{routerMetrics.memory_usage_percent}%</p>
                <p className="mt-1 text-xs text-zinc-500">
                  {formatBytes(routerMetrics.memory_used_bytes)} used of {formatBytes(routerMetrics.memory_total_bytes)}
                  {' · '}{formatBytes(routerMetrics.memory_free_bytes)} free
                </p>
                <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/10">
                  <div
                    className="h-full rounded-full bg-indigo-400"
                    style={{ width: `${Math.min(100, Math.max(0, routerMetrics.memory_usage_percent))}%` }}
                  />
                </div>
              </div>
              <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
                <p className="text-xs text-zinc-400">Uptime</p>
                <p className="mt-2 text-lg font-semibold text-white">{routerMetrics.uptime || 'Unavailable'}</p>
              </div>
              <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
                <p className="text-xs text-zinc-400">Active Hotspot Users</p>
                <p className="mt-2 text-2xl font-bold text-white">{formatNumber(routerMetrics.active_hotspot_users)}</p>
              </div>
            </div>

            <section className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
              <div className="mb-3 flex items-center justify-between">
                <h3 className="text-sm font-semibold text-white">Interface Traffic</h3>
                <span className="text-[11px] text-zinc-500">
                  Updated {timeAgo(routerMetrics.captured_at)}
                </span>
              </div>
              {routerMetrics.interfaces.length ? (
                <div className="space-y-2">
                  {routerMetrics.interfaces.map((networkInterface) => (
                    <div
                      key={networkInterface.name}
                      className="flex flex-col gap-1 rounded-lg bg-black/20 px-3 py-2 text-xs sm:flex-row sm:items-center sm:justify-between"
                    >
                      <span className="font-medium text-white">{networkInterface.name}</span>
                      <div className="flex gap-4 text-zinc-400">
                        <span>RX {formatBytes(networkInterface.rx_bytes)}</span>
                        <span>TX {formatBytes(networkInterface.tx_bytes)}</span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-zinc-500">No interface traffic data reported.</p>
              )}
            </section>
          </div>
        )}
        {routerMetricsLoading && routerMetrics && (
          <p className="mt-3 flex items-center gap-2 text-[11px] text-zinc-500">
            <RefreshCw className="h-3 w-3 animate-spin" /> Refreshing live metrics…
          </p>
        )}
      </Modal>
      <Modal
        open={showMobilePreview}
        onClose={() => setShowMobilePreview(false)}
        title="Mobile Portal Preview"
        description="Preview your captive portal with the current branding and active plans."
        size="lg"
      >
        <MobilePortalPreview
          tenantId={tenant.id}
          businessName={tenant.business_name}
          headline={branding.welcome_headline}
          logoUrl={branding.logo_url}
          brandColor={branding.brand_color}
          hotspotName={routers[0]?.shortname || routers[0]?.nasname || tenant.business_name}
          nasId={routers.find((router) => router.is_online)?.id || routers[0]?.id || null}
          plans={plans}
          onClose={() => setShowMobilePreview(false)}
        />
      </Modal>
    </div>
  );
}
