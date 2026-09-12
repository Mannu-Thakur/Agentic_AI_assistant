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
  const [menuCoords, setMenuCoords] = useState<{
    top?: number;
    bottom?: number;
    left?: number;
    right?: number;
    openUpward: boolean;
  } | null>(null);

  const containerRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  const selectedOption = options.find((opt) => opt.value === value) || options[0];

  const updatePosition = useCallback(() => {
    if (!buttonRef.current) return;
    const rect = buttonRef.current.getBoundingClientRect();
    const spaceBelow = window.innerHeight - rect.bottom;
    const openUpward = spaceBelow < 250 && rect.top > 250;

    let coords: {
      top?: number;
      bottom?: number;
      left?: number;
      right?: number;
      openUpward: boolean;
    } = { openUpward };

    if (openUpward) {
      coords.bottom = window.innerHeight - rect.top + 6;
    } else {
      coords.top = rect.bottom + 6;
    }

    if (align === 'left') {
      coords.left = Math.max(12, Math.min(rect.left, window.innerWidth - 300));
    } else {
      coords.right = Math.max(12, window.innerWidth - rect.right);
    }

    setMenuCoords(coords);
  }, [align]);

  useEffect(() => {
    if (!isOpen) return;

    updatePosition();

    const handleScroll = (event: Event) => {
      if (menuRef.current && menuRef.current.contains(event.target as Node)) {
        return;
      }
      setIsOpen(false);
    };

    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as Node;
      if (
        containerRef.current &&
        !containerRef.current.contains(target) &&
        menuRef.current &&
        !menuRef.current.contains(target)
      ) {
        setIsOpen(false);
      }
    };

    window.addEventListener('scroll', handleScroll, true);
    window.addEventListener('resize', updatePosition);
    document.addEventListener('mousedown', handleClickOutside);

    return () => {
      window.removeEventListener('scroll', handleScroll, true);
      window.removeEventListener('resize', updatePosition);
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen, updatePosition]);

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
    <div
      ref={containerRef}
      className={`relative inline-block ${className} ${isOpen ? 'z-[999]' : 'z-10'}`}
    >
      <button
        ref={buttonRef}
        type="button"
        disabled={disabled}
        onClick={() => {
          if (!isOpen) updatePosition();
          setIsOpen((prev) => !prev);
        }}
        onKeyDown={handleKeyDown}
        className={`group flex items-center justify-between gap-2.5 px-3.5 py-2 rounded-xl
          bg-surface-2/80 hover:bg-surface-3 text-xs font-semibold text-foreground
          transition-all duration-200 border border-border/80 shadow-xs outline-none backdrop-blur-md
          focus-visible:ring-2 focus-visible:ring-primary/40 active:scale-[0.98]
          disabled:opacity-50 disabled:cursor-not-allowed ${buttonClassName}`}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
      >
        <div className="flex items-center gap-2 min-w-0">
          {selectedOption?.color ? (
            <span
              className="w-2.5 h-2.5 rounded-full flex-shrink-0 shadow-xs"
              style={{ backgroundColor: selectedOption.color }}
            />
          ) : SelectedIcon ? (
            <SelectedIcon className="w-3.5 h-3.5 text-primary flex-shrink-0 transition-colors" />
          ) : null}

          <span className="truncate max-w-[150px] text-xs font-medium text-foreground">
            {selectedOption?.label || placeholder}
          </span>
        </div>

        <ChevronDown
          className={`w-3.5 h-3.5 text-foreground-3 group-hover:text-foreground-2 transition-transform duration-200 flex-shrink-0 ${
            isOpen ? 'rotate-180 text-primary' : ''
          }`}
        />
      </button>

      {isOpen && menuCoords && (
        <div
          ref={menuRef}
          role="listbox"
          style={{
            position: 'fixed',
            top: menuCoords.top !== undefined ? `${menuCoords.top}px` : undefined,
            bottom: menuCoords.bottom !== undefined ? `${menuCoords.bottom}px` : undefined,
            left: menuCoords.left !== undefined ? `${menuCoords.left}px` : undefined,
            right: menuCoords.right !== undefined ? `${menuCoords.right}px` : undefined,
            zIndex: 99999,
          }}
          className={`min-w-[210px] max-w-[340px] p-1.5 rounded-2xl
            bg-surface/98 border border-border/90 shadow-[0_20px_60px_rgba(0,0,0,0.65)] backdrop-blur-2xl animate-scale-in
            flex flex-col gap-0.5 max-h-64 overflow-y-auto custom-scrollbar ${menuClassName}`}
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
                className={`w-full flex items-center justify-between gap-2.5 px-3 py-2 rounded-xl text-xs text-left
                  transition-all duration-150 cursor-pointer group ${
                    isSelected
                      ? 'bg-primary/15 text-foreground font-semibold shadow-xs'
                      : 'text-foreground-2 hover:text-foreground hover:bg-surface-2/90'
                  }`}
              >
                <div className="flex items-center gap-2.5 min-w-0 flex-1">
                  {option.color ? (
                    <span
                      className="w-2.5 h-2.5 rounded-full flex-shrink-0 shadow-xs"
                      style={{ backgroundColor: option.color }}
                    />
                  ) : OptionIcon ? (
                    <OptionIcon
                      className={`w-3.5 h-3.5 flex-shrink-0 transition-colors ${
                        isSelected ? 'text-primary' : 'text-foreground-3 group-hover:text-foreground-2'
                      }`}
                    />
                  ) : null}

                  <div className="min-w-0 flex-1">
                    <p className="truncate leading-snug font-medium text-foreground">{option.label}</p>
                    {option.description && (
                      <p className="text-[10px] text-foreground-3 truncate leading-normal mt-0.5">
                        {option.description}
                      </p>
                    )}
                  </div>
                </div>

                {isSelected && <Check className="w-3.5 h-3.5 text-primary flex-shrink-0 stroke-[2.5]" />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
