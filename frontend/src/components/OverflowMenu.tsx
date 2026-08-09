import { useState, useEffect, useRef, useCallback } from 'react';
import { IconMoreHorizontal } from './icons';

interface OverflowItem {
  label: string;
  onClick: () => void;
  danger?: boolean;
  disabled?: boolean;
}

interface OverflowMenuProps {
  items: OverflowItem[];
}

export function OverflowMenu({ items }: OverflowMenuProps) {
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  const close = useCallback(() => {
    setOpen(false);
    triggerRef.current?.focus();
  }, []);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        close();
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open, close]);

  // Keyboard navigation
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      close();
      return;
    }
    if (!open) return;

    const focusable = menuRef.current?.querySelectorAll<HTMLButtonElement>(
      'button:not(:disabled)'
    );
    if (!focusable || focusable.length === 0) return;
    const arr = Array.from(focusable);
    const idx = arr.indexOf(document.activeElement as HTMLButtonElement);

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      arr[(idx + 1) % arr.length]?.focus();
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      arr[(idx - 1 + arr.length) % arr.length]?.focus();
    }
  };

  const visibleItems = items.filter(i => !i.disabled);
  if (visibleItems.length === 0) return null;

  return (
    <div className="overflow-menu" ref={menuRef} onKeyDown={handleKeyDown}>
      <button
        ref={triggerRef}
        className="overflow-trigger"
        onClick={() => setOpen(o => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="More actions"
        title="More actions"
      >
        <IconMoreHorizontal size={18} />
      </button>
      {open && (
        <div className="overflow-dropdown" role="menu">
          {visibleItems.map((item, i) => (
            <button
              key={i}
              className={`overflow-item ${item.danger ? 'overflow-item-danger' : ''}`}
              role="menuitem"
              onClick={() => { item.onClick(); close(); }}
            >
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
