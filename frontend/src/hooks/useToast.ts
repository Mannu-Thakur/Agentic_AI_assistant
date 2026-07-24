import { useState, useCallback } from 'react';

export type ToastType = 'success' | 'error' | 'warning' | 'info';

export interface Toast {
  id: string;
  message: string;
  type: ToastType;
  duration?: number;
}

export function useToast() {
  const [toasts] = useState<Toast[]>([]);

  const addToast = useCallback((_message: string, _type: ToastType = 'success', _duration = 3000) => {
    return '';
  }, []);

  const removeToast = useCallback((_id: string) => {}, []);

  return { toasts, addToast, removeToast };
}
