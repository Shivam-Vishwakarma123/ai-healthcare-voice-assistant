import { useEffect, useRef } from "react";

export default function Modal({ isOpen, onClose, title, children, size = "medium", language = "en" }) {
  const dialogRef = useRef(null);
  const hi = language === "hi";

  useEffect(() => {
    if (!isOpen) return undefined;

    // Focus management
    const previouslyFocused = document.activeElement;
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
      previouslyFocused?.focus();
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

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
        className={`cv-modal cv-modal-${size}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="cv-modal-title"
      >
        <div className="cv-modal-header">
          <h2 id="cv-modal-title">{title}</h2>
          <button
            className="cv-modal-close"
            type="button"
            onClick={onClose}
            aria-label={hi ? "बंद करें" : "Close"}
          >
            ×
          </button>
        </div>
        <div className="cv-modal-body">
          {children}
        </div>
      </div>
    </div>
  );
}
