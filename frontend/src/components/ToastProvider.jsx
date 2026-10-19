import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { isDuplicateToast, sanitizeToastMessage } from "../services/toastPolicy";

const ToastContext = createContext(null);
const durations = { success: 4800, error: 6200, info: 4800, warning: 5600 };

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const timers = useRef(new Map());
  const recent = useRef(new Map());

  const dismiss = useCallback((id) => {
    const timer = timers.current.get(id);
    if (timer) clearTimeout(timer);
    timers.current.delete(id);
    setToasts((items) => items.filter((item) => item.id !== id));
  }, []);

  const showToast = useCallback((message, type = "info", options = {}) => {
    const text = sanitizeToastMessage(message);
    if (!text) return;
    const key = `${type}:${text}`;
    const now = Date.now();
    if (isDuplicateToast(key, now, recent.current)) return;
    const id = globalThis.crypto?.randomUUID?.() || `${now}-${Math.random()}`;
    setToasts((items) => [...items.slice(-3), { id, message: text, type }]);
    timers.current.set(id, setTimeout(() => dismiss(id), options.duration ?? durations[type] ?? 4800));
  }, [dismiss]);

  useEffect(() => () => timers.current.forEach(clearTimeout), []);

  return (
    <ToastContext.Provider value={showToast}>
      {children}
      <div className="cv-toast-region" aria-label="Notifications" aria-live="polite" aria-relevant="additions">
        {toasts.map((toast) => (
          <div className={`cv-toast cv-toast-${toast.type}`} key={toast.id} role={toast.type === "error" ? "alert" : "status"}>
            <span className="cv-toast-icon" aria-hidden="true">{toast.type === "success" ? "✓" : toast.type === "error" ? "!" : toast.type === "warning" ? "⚠" : "i"}</span>
            <span className="cv-toast-message">{toast.message}</span>
            <button type="button" className="cv-toast-dismiss" onClick={() => dismiss(toast.id)} aria-label="Dismiss notification">×</button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const showToast = useContext(ToastContext);
  if (!showToast) throw new Error("useToast must be used within ToastProvider");
  return showToast;
}
