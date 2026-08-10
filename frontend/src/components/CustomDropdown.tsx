import React, { useState, useRef, useEffect } from 'react';
import { playSound } from '../utils/audio';

export interface DropdownOption {
  value: string;
  label: string;
}

export interface CustomDropdownProps {
  options: DropdownOption[];
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  id?: string;
  ariaLabel?: string;
}

export function CustomDropdown({
  options,
  value,
  onChange,
  disabled = false,
  id,
  ariaLabel = 'Select option',
}: CustomDropdownProps) {
  const [isOpen, setIsOpen] = useState(false);
  const selectedIndex = options.findIndex(o => o.value === value);
  const [highlightedIndex, setHighlightedIndex] = useState(selectedIndex >= 0 ? selectedIndex : 0);
  const containerRef = useRef<HTMLDivElement>(null);

  const selectedOption = options.find(o => o.value === value) || options[0];

  useEffect(() => {
    const idx = options.findIndex(o => o.value === value);
    if (idx >= 0) setHighlightedIndex(idx);
  }, [value, options]);

  const [openUp, setOpenUp] = useState(false);

  useEffect(() => {
    if (!isOpen || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const spaceBelow = window.innerHeight - rect.bottom;
    if (spaceBelow < 220 && rect.top > 220) {
      setOpenUp(true);
    } else {
      setOpenUp(false);
    }
  }, [isOpen]);

  // Click outside to close
  useEffect(() => {
    if (!isOpen) return;
    const handleOutsideClick = (e: MouseEvent | TouchEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleOutsideClick);
    document.addEventListener('touchstart', handleOutsideClick);
    return () => {
      document.removeEventListener('mousedown', handleOutsideClick);
      document.removeEventListener('touchstart', handleOutsideClick);
    };
  }, [isOpen]);

  const handleSelect = (optionValue: string) => {
    if (disabled) return;
    playSound('select');
    onChange(optionValue);
    setIsOpen(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (disabled) return;

    if (e.key === 'Escape') {
      if (isOpen) {
        e.preventDefault();
        e.stopPropagation();
        setIsOpen(false);
      }
      return;
    }

    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      if (!isOpen) {
        setIsOpen(true);
      } else {
        if (options[highlightedIndex]) {
          handleSelect(options[highlightedIndex].value);
        }
      }
      return;
    }

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (!isOpen) {
        setIsOpen(true);
      } else {
        setHighlightedIndex(prev => (prev + 1) % options.length);
      }
      return;
    }

    if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (!isOpen) {
        setIsOpen(true);
      } else {
        setHighlightedIndex(prev => (prev - 1 + options.length) % options.length);
      }
      return;
    }
  };

  return (
    <div
      ref={containerRef}
      className={`custom-dropdown-container ${disabled ? 'disabled' : ''} ${isOpen ? 'open' : ''} ${openUp ? 'open-up' : ''}`}
    >
      <button
        type="button"
        id={id}
        className="custom-dropdown-trigger"
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-label={ariaLabel}
        disabled={disabled}
        onClick={() => !disabled && setIsOpen(prev => !prev)}
        onKeyDown={handleKeyDown}
      >
        <span className="custom-dropdown-value">{selectedOption ? selectedOption.label : value}</span>
        <span className="custom-dropdown-arrow" aria-hidden="true">
          ▾
        </span>
      </button>

      {isOpen && (
        <ul
          className="custom-dropdown-menu"
          role="listbox"
          tabIndex={-1}
          aria-activedescendant={options[highlightedIndex] ? `opt-${options[highlightedIndex].value}` : undefined}
        >
          {options.map((option, idx) => {
            const isSelected = option.value === value;
            const isHighlighted = idx === highlightedIndex;
            return (
              <li
                key={option.value}
                id={`opt-${option.value}`}
                role="option"
                aria-selected={isSelected}
                className={`custom-dropdown-option ${isSelected ? 'selected' : ''} ${
                  isHighlighted ? 'highlighted' : ''
                }`}
                onClick={() => handleSelect(option.value)}
                onMouseEnter={() => setHighlightedIndex(idx)}
              >
                <span className="option-label">{option.label}</span>
                {isSelected && <span className="option-check" aria-hidden="true">✓</span>}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
