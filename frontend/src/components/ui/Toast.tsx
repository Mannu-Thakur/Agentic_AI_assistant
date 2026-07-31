import type { Toast as ToastItem } from '../../hooks/useToast';
import { CheckCircle2, XCircle, AlertTriangle, Info, X } from 'lucide-react';

export function ToastContainer({
  toasts,
  onRemove,
}: {
  toasts: ToastItem[];
  onRemove: (id: string) => void;
}) {
  if (!toasts || toasts.length === 0) return null;

  return (
    <div className="fixed top-5 right-5 z-[9999] flex flex-col gap-2.5 max-w-sm w-full pointer-events-none px-4 sm:px-0">
      {toasts.map((toast) => {
        const isSuccess = toast.type === 'success';
        const isError = toast.type === 'error';
        const isWarning = toast.type === 'warning';

        return (
          <div
            key={toast.id}
            className={`pointer-events-auto flex items-start justify-between gap-3 p-3.5 rounded-xl border shadow-xl backdrop-blur-xl transition-all duration-200 ${
              isSuccess
                ? 'bg-emerald-950/90 border-emerald-500/40 text-emerald-200'
                : isError
                ? 'bg-rose-950/90 border-rose-500/40 text-rose-200'
                : isWarning
                ? 'bg-amber-950/90 border-amber-500/40 text-amber-200'
                : 'bg-slate-900/90 border-slate-700/60 text-slate-200'
            }`}
          >
            <div className="flex items-start gap-2.5 pt-0.5">
              {isSuccess && <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0 mt-0.5" />}
              {isError && <XCircle className="w-4 h-4 text-rose-400 flex-shrink-0 mt-0.5" />}
              {isWarning && <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />}
              {!isSuccess && !isError && !isWarning && (
                <Info className="w-4 h-4 text-sky-400 flex-shrink-0 mt-0.5" />
              )}
              <p className="text-xs font-medium leading-snug break-words">{toast.message}</p>
            </div>
            <button
              onClick={() => onRemove(toast.id)}
              className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-white/10 transition-colors flex-shrink-0"
              aria-label="Close notification"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
