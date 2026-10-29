import { useEffect, useRef } from "react";

// Accessible modal dialog primitive managing keyboard navigation, focus trap, and background scroll locking.
export default function Modal({
  isOpen,
  onClose,
  title,
  subtitle = null,
  headerBadge = null,
  children,
  footer = null,
  size = "medium",
  language = "en",
  className = "",
  bodyClassName = "",
  triggerRef = null,
  ariaDescribedBy = null,
}) {
  const dialogRef = useRef(null);
  const hi = language === "hi";

  useEffect(() => {
    if (!isOpen) return undefined;

    // Focus management: remember trigger or active element
    const previouslyFocused = triggerRef?.current || document.activeElement;
    dialogRef.current?.querySelector("button, input, select, textarea, [href], [tabindex]:not([tabindex='-1'])")?.focus();

    // Prevent background scroll
    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    // Keyboard handlers
    function handleKeyDown(event) {
      if (event.key === "Escape") {
        onClose();
        return;
      }

      // Focus trap
      if (event.key === "Tab" && dialogRef.current) {
        const focusableElements = [
          ...dialogRef.current.querySelectorAll(
            "button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [href], [tabindex]:not([tabindex='-1'])"
          ),
        ];
        if (focusableElements.length === 0) return;
        const firstElement = focusableElements[0];
        const lastElement = focusableElements[focusableElements.length - 1];

        if (event.shiftKey && document.activeElement === firstElement) {
          event.preventDefault();
          lastElement?.focus();
        } else if (!event.shiftKey && document.activeElement === lastElement) {
          event.preventDefault();
          firstElement?.focus();
        }
      }
    }

    window.addEventListener("keydown", handleKeyDown);

    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = originalOverflow;
      if (triggerRef?.current && typeof triggerRef.current.focus === "function") {
        triggerRef.current.focus();
      } else if (previouslyFocused && typeof previouslyFocused.focus === "function") {
        previouslyFocused.focus();
      }
    };
  }, [isOpen, onClose, triggerRef]);

  if (!isOpen) return null;

  const descId = subtitle ? "cv-modal-subtitle" : ariaDescribedBy;

  return (
    <div
      className="cv-modal-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <div
        ref={dialogRef}
        className={`cv-modal cv-modal-${size} ${className}`.trim()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="cv-modal-title"
        aria-describedby={descId || undefined}
      >
        <div className="cv-modal-header">
          <div className="cv-modal-title-group">
            <div className="cv-modal-title-row">
              <h2 id="cv-modal-title">{title}</h2>
              {headerBadge}
            </div>
            {subtitle && (
              <p id="cv-modal-subtitle" className="cv-modal-subtitle">
                {subtitle}
              </p>
            )}
          </div>
          <button
            className="cv-modal-close"
            type="button"
            onClick={onClose}
            aria-label={hi ? "बंद करें" : "Close"}
          >
            ×
          </button>
        </div>
        <div className={`cv-modal-body ${bodyClassName}`.trim()}>
          {children}
        </div>
        {footer && <div className="cv-modal-footer">{footer}</div>}
      </div>
    </div>
  );
}
