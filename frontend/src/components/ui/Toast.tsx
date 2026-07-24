import type { Toast as ToastItem } from '../../hooks/useToast';

// ── Toast Container ─────────────────────────────────────────
export function ToastContainer({
  toasts: _toasts,
  onRemove: _onRemove,
}: {
  toasts: ToastItem[];
  onRemove: (id: string) => void;
}) {
  return null;
}
