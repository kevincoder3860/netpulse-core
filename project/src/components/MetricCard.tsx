import { type ReactNode } from 'react';

interface MetricCardProps {
  label: string;
  value: string;
  icon: ReactNode;
  trend?: string;
  trendUp?: boolean;
  accent?: 'indigo' | 'emerald' | 'amber' | 'sky' | 'rose' | 'violet';
  onClick?: () => void;
}

const accentMap = {
  indigo: 'from-indigo-500/20 to-indigo-500/5 border-indigo-500/20 text-indigo-300',
  emerald: 'from-emerald-500/20 to-emerald-500/5 border-emerald-500/20 text-emerald-300',
  amber: 'from-amber-500/20 to-amber-500/5 border-amber-500/20 text-amber-300',
  sky: 'from-sky-500/20 to-sky-500/5 border-sky-500/20 text-sky-300',
  rose: 'from-rose-500/20 to-rose-500/5 border-rose-500/20 text-rose-300',
  violet: 'from-violet-500/20 to-violet-500/5 border-violet-500/20 text-violet-300',
};

const iconBgMap = {
  indigo: 'bg-indigo-500/15 text-indigo-400',
  emerald: 'bg-emerald-500/15 text-emerald-400',
  amber: 'bg-amber-500/15 text-amber-400',
  sky: 'bg-sky-500/15 text-sky-400',
  rose: 'bg-rose-500/15 text-rose-400',
  violet: 'bg-violet-500/15 text-violet-400',
};

export default function MetricCard({ label, value, icon, trend, trendUp, accent = 'indigo', onClick }: MetricCardProps) {
  const className = `relative overflow-hidden rounded-2xl border bg-gradient-to-br p-5 backdrop-blur-xl ${accentMap[accent]} ${onClick ? 'cursor-pointer transition-transform hover:-translate-y-0.5 hover:brightness-110 focus:outline-none focus:ring-2 focus:ring-cyan-300/50' : ''}`;
  const content = (
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-zinc-400">{label}</p>
          <p className="mt-2 text-2xl font-bold text-white">{value}</p>
          {trend && (
            <p className={`mt-1.5 text-xs font-medium ${trendUp ? 'text-emerald-400' : 'text-rose-400'}`}>
              {trend}
            </p>
          )}
        </div>
        <div className={`rounded-xl p-2.5 ${iconBgMap[accent]}`}>
          {icon}
        </div>
      </div>
  );

  return onClick ? <button type="button" onClick={onClick} className={`${className} w-full text-left`}>{content}</button> : <div className={className}>{content}</div>;
}
