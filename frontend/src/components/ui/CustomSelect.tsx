import React, { useState, useRef, useEffect, useCallback } from 'react';
import { ChevronDown, Check } from 'lucide-react';

export interface SelectOption {
  value: string;
  label: string;
  description?: string;
  icon?: React.ElementType;
  color?: string;
}

export interface CustomSelectProps {
  options: SelectOption[];
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
  buttonClassName?: string;
  menuClassName?: string;
  align?: 'left' | 'right';
  disabled?: boolean;
}

export function CustomSelect({
  options,
  value,
  onChange,
  placeholder = 'Select option',
  className = '',
  buttonClassName = '',
  menuClassName = '',
  align = 'right',
  disabled = false,
}: CustomSelectProps) {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const selectedOption = options.find((opt) => opt.value === value) || options[0];

  // Close dropdown on click outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  // Handle keyboard events
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (disabled) return;

      if (e.key === 'Escape') {
        setIsOpen(false);
      } else if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        setIsOpen((prev) => !prev);
      } else if (e.key === 'ArrowDown' && isOpen) {
        e.preventDefault();
        const currentIndex = options.findIndex((opt) => opt.value === value);
        const nextIndex = (currentIndex + 1) % options.length;
        onChange(options[nextIndex].value);
      } else if (e.key === 'ArrowUp' && isOpen) {
        e.preventDefault();
        const currentIndex = options.findIndex((opt) => opt.value === value);
        const prevIndex = (currentIndex - 1 + options.length) % options.length;
        onChange(options[prevIndex].value);
      }
    },
    [disabled, isOpen, options, value, onChange]
  );

  const SelectedIcon = selectedOption?.icon;

  return (
    <div ref={containerRef} className={`relative inline-block ${className}`}>
      <button
        type="button"
        disabled={disabled}
        onClick={() => setIsOpen((prev) => !prev)}
        onKeyDown={handleKeyDown}
        className={`group flex items-center justify-between gap-2 px-2.5 py-1 rounded-full
          bg-surface-2/60 hover:bg-surface-3/90 text-xs font-semibold text-foreground
          transition-all duration-200 border border-border/70 shadow-xs outline-none backdrop-blur-md
          focus-visible:ring-2 focus-visible:ring-accent/40 active:scale-[0.97]
          disabled:opacity-50 disabled:cursor-not-allowed ${buttonClassName}`}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
      >
        <div className="flex items-center gap-2 min-w-0">
          {selectedOption?.color ? (
            <span
              className="w-2 h-2 rounded-full flex-shrink-0 shadow-xs"
              style={{ backgroundColor: selectedOption.color }}
            />
          ) : SelectedIcon ? (
            <SelectedIcon className="w-3.5 h-3.5 text-accent flex-shrink-0 transition-colors" />
          ) : null}

          <span className="truncate max-w-[140px] text-xs font-medium">{selectedOption?.label || placeholder}</span>
        </div>

        <ChevronDown
          className={`w-3.5 h-3.5 text-foreground-3 group-hover:text-foreground-2 transition-transform duration-200 flex-shrink-0 ${
            isOpen ? 'rotate-180 text-foreground' : ''
          }`}
        />
      </button>

      {isOpen && (
        <div
          role="listbox"
          className={`absolute top-full mt-1.5 min-w-[180px] max-w-[260px] z-50 p-1.5 rounded-2xl
            bg-surface/95 dark:bg-surface/95 border border-border/80 shadow-xl backdrop-blur-xl animate-scale-in
            flex flex-col gap-0.5 max-h-64 overflow-y-auto custom-scrollbar ${
              align === 'right' ? 'right-0' : 'left-0'
            } ${menuClassName}`}
        >
          {options.map((option) => {
            const isSelected = option.value === value;
            const OptionIcon = option.icon;

            return (
              <button
                key={option.value}
                type="button"
                role="option"
                aria-selected={isSelected}
                onClick={() => {
                  onChange(option.value);
                  setIsOpen(false);
                }}
                className={`w-full flex items-center justify-between gap-2.5 px-2.5 py-1.5 rounded-xl text-xs text-left
                  transition-all duration-150 cursor-pointer group ${
                    isSelected
                      ? 'bg-accent/15 text-foreground font-semibold shadow-xs'
                      : 'text-foreground-2 hover:text-foreground hover:bg-surface-2/80'
                  }`}
              >
                <div className="flex items-center gap-2 min-w-0 flex-1">
                  {option.color ? (
                    <span
                      className="w-2.5 h-2.5 rounded-full flex-shrink-0 shadow-xs"
                      style={{ backgroundColor: option.color }}
                    />
                  ) : OptionIcon ? (
                    <OptionIcon
                      className={`w-3.5 h-3.5 flex-shrink-0 transition-colors ${
                        isSelected ? 'text-accent' : 'text-foreground-3 group-hover:text-foreground-2'
                      }`}
                    />
                  ) : null}

                  <div className="min-w-0 flex-1">
                    <p className="truncate leading-snug font-medium text-foreground">{option.label}</p>
                    {option.description && (
                      <p className="text-[9px] text-foreground-3/80 truncate leading-none mt-0.5">
                        {option.description}
                      </p>
                    )}
                  </div>
                </div>

                {isSelected && <Check className="w-3.5 h-3.5 text-accent flex-shrink-0 stroke-[2.5]" />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
