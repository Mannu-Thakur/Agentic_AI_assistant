import { LucideIcon } from 'lucide-react';

interface SidebarItemProps {
  icon: LucideIcon;
  label: string;
  active?: boolean;
  onClick?: () => void;
  badge?: string | number;
}

export function SidebarItem({ icon: Icon, label, active, onClick, badge }: SidebarItemProps) {
  return (
    <button
      onClick={onClick}
      className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm transition font-medium ${
        active
          ? 'bg-blue-600/20 text-blue-400 border border-blue-500/30'
          : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
      }`}
    >
      <div className="flex items-center gap-2.5">
        <Icon className={`w-4 h-4 ${active ? 'text-blue-400' : 'text-slate-400'}`} />
        <span>{label}</span>
      </div>
      {badge !== undefined && (
        <span className="px-2 py-0.5 text-xs bg-slate-800 text-slate-300 rounded-full font-mono">
          {badge}
        </span>
      )}
    </button>
  );
}
