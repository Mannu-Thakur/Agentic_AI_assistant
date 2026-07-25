import { useState, useEffect, useRef } from 'react';

interface LogoProps {
  collapsed?: boolean;
  size?: number;
  className?: string;
  isStreaming?: boolean;
  isTyping?: boolean;
}

export default function Logo({
  collapsed = false,
  size = 32,
  className = '',
  isStreaming = false,
  isTyping = false,
}: LogoProps) {
  const [eyeOffset, setEyeOffset] = useState({ x: 0, y: 0 });
  const [isBlinking, setIsBlinking] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);

  // 1. Idle wandering eyes timer
  useEffect(() => {
    if (isStreaming || isTyping) return;

    const interval = setInterval(() => {
      // 30% chance to blink
      if (Math.random() < 0.3) {
        setIsBlinking(true);
        setTimeout(() => setIsBlinking(false), 180);
      } else {
        // Wandering gaze
        const dx = (Math.random() - 0.5) * 6; // -3 to 3px
        const dy = (Math.random() - 0.5) * 4; // -2 to 2px
        setEyeOffset({ x: dx, y: dy });
      }
    }, 2500);

    return () => clearInterval(interval);
  }, [isStreaming, isTyping]);

  // 2. Mouse tracking gaze
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!containerRef.current || isStreaming) return;
      const rect = containerRef.current.getBoundingClientRect();
      const centerX = rect.left + rect.width / 2;
      const centerY = rect.top + rect.height / 2;
      const angle = Math.atan2(e.clientY - centerY, e.clientX - centerX);
      const dist = Math.min(4, Math.hypot(e.clientX - centerX, e.clientY - centerY) / 80);
      setEyeOffset({
        x: Math.cos(angle) * dist,
        y: Math.sin(angle) * dist,
      });
    };

    window.addEventListener('mousemove', handleMouseMove);
    return () => window.removeEventListener('mousemove', handleMouseMove);
  }, [isStreaming]);

  // 3. Scanning eyes while streaming/generating
  useEffect(() => {
    if (!isStreaming) return;
    let step = 0;
    const scanInterval = setInterval(() => {
      step = (step + 1) % 4;
      const positions = [
        { x: -3, y: 0 },
        { x: 3, y: 0 },
        { x: 2, y: -1 },
        { x: -2, y: 1 },
      ];
      setEyeOffset(positions[step]);
    }, 350);

    return () => clearInterval(scanInterval);
  }, [isStreaming]);

  return (
    <div
      ref={containerRef}
      className={`flex items-center gap-2.5 select-none group/logo ${className}`}
    >
      {/* Interactive Vector AI Bot Head with Wondering Eyes */}
      <div
        className="relative flex items-center justify-center flex-shrink-0 transition-transform duration-300 group-hover/logo:scale-105"
        style={{ width: size, height: size }}
      >
        <svg
          width={size}
          height={size}
          viewBox="0 0 48 48"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          className="overflow-visible"
        >
          <defs>
            {/* Visor Gradient */}
            <linearGradient id="visorGrad" x1="8" y1="14" x2="40" y2="38" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stopColor="#1e293b" />
              <stop offset="100%" stopColor="#0f172a" />
            </linearGradient>

            {/* Eye Glow Filter */}
            <filter id="eyeGlow" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="1.5" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>

            {/* Antenna Light Glow */}
            <filter id="antennaGlow" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="2" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>

          {/* Antenna Pole & Gem */}
          <line x1="24" y1="10" x2="24" y2="4" stroke="#64748b" strokeWidth="2.5" strokeLinecap="round" />
          <circle
            cx="24"
            cy="4"
            r="3"
            fill={isStreaming ? '#10b981' : '#38bdf8'}
            filter="url(#antennaGlow)"
            className={isStreaming ? 'animate-pulse' : ''}
          />

          {/* Outer Helmet Outline */}
          <rect
            x="6"
            y="10"
            width="36"
            height="30"
            rx="12"
            fill="url(#visorGrad)"
            stroke="rgba(255,255,255,0.2)"
            strokeWidth="2"
          />

          {/* Side Ears */}
          <rect x="2" y="21" width="4" height="8" rx="2" fill="#334155" />
          <rect x="42" y="21" width="4" height="8" rx="2" fill="#334155" />

          {/* Visor Screen Glass */}
          <rect
            x="10"
            y="15"
            width="28"
            height="20"
            rx="8"
            fill="#090d16"
            stroke="rgba(56, 189, 248, 0.3)"
            strokeWidth="1"
          />

          {/* Interactive Wondering Eyes Group */}
          <g
            style={{
              transform: `translate(${eyeOffset.x}px, ${eyeOffset.y}px) scaleY(${isBlinking ? 0.1 : 1})`,
              transformOrigin: '24px 25px',
              transition: isBlinking ? 'transform 0.08s ease' : 'transform 0.25s cubic-bezier(0.16, 1, 0.3, 1)',
            }}
          >
            {/* Left Eye Pupil */}
            <ellipse
              cx="18"
              cy="25"
              rx={isStreaming ? 3.5 : 3}
              ry={isStreaming ? 3.5 : 3.5}
              fill={isStreaming ? '#34d399' : '#38bdf8'}
              filter="url(#eyeGlow)"
            />
            {/* Left Eye Glint */}
            <circle cx="17" cy="24" r="1" fill="#ffffff" opacity="0.9" />

            {/* Right Eye Pupil */}
            <ellipse
              cx="30"
              cy="25"
              rx={isStreaming ? 3.5 : 3}
              ry={isStreaming ? 3.5 : 3.5}
              fill={isStreaming ? '#34d399' : '#38bdf8'}
              filter="url(#eyeGlow)"
            />
            {/* Right Eye Glint */}
            <circle cx="29" cy="24" r="1" fill="#ffffff" opacity="0.9" />
          </g>

          {/* Subtly Glowing Smile / Status Line */}
          <path
            d={isStreaming ? 'M 20 31 Q 24 33 28 31' : 'M 21 31 Q 24 32.5 27 31'}
            stroke={isStreaming ? '#34d399' : '#64748b'}
            strokeWidth="1.5"
            strokeLinecap="round"
            fill="none"
            opacity="0.85"
          />
        </svg>
      </div>

      {!collapsed && (
        <div className="flex items-baseline gap-0.5 leading-none">
          <span className="font-bold text-[15px] tracking-tight text-foreground">
            open<span className="text-blue-400">Chat</span>
          </span>
        </div>
      )}
    </div>
  );
}
