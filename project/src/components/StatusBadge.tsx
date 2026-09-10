interface StatusBadgeProps {
  status: string;
}

const statusConfig: Record<string, { label: string; className: string; dot: string }> = {
  active: { label: 'Active', className: 'bg-emerald-500/10 text-emerald-300 border-emerald-500/20', dot: 'bg-emerald-400' },
  suspended: { label: 'Suspended', className: 'bg-rose-500/10 text-rose-300 border-rose-500/20', dot: 'bg-rose-400' },
  SUSPENDED: { label: 'Suspended', className: 'bg-rose-500/10 text-rose-300 border-rose-500/20', dot: 'bg-rose-400' },
  CLOSED: { label: 'Closed', className: 'bg-zinc-500/10 text-zinc-400 border-zinc-500/20', dot: 'bg-zinc-500' },
  ACTIVE: { label: 'Active', className: 'bg-emerald-500/10 text-emerald-300 border-emerald-500/20', dot: 'bg-emerald-400' },
  pending: { label: 'Pending', className: 'bg-amber-500/10 text-amber-300 border-amber-500/20', dot: 'bg-amber-400' },
  completed: { label: 'Completed', className: 'bg-emerald-500/10 text-emerald-300 border-emerald-500/20', dot: 'bg-emerald-400' },
  failed: { label: 'Failed', className: 'bg-rose-500/10 text-rose-300 border-rose-500/20', dot: 'bg-rose-400' },
  online: { label: 'Online', className: 'bg-emerald-500/10 text-emerald-300 border-emerald-500/20', dot: 'bg-emerald-400' },
  offline: { label: 'Offline', className: 'bg-zinc-500/10 text-zinc-400 border-zinc-500/20', dot: 'bg-zinc-500' },
};

export default function StatusBadge({ status }: StatusBadgeProps) {
  const config = statusConfig[status] || statusConfig.pending;
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${config.className}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${config.dot} ${status === 'online' ? 'animate-pulse' : ''}`} />
      {config.label}
    </span>
  );
}
