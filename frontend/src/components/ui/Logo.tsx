interface LogoProps {
  collapsed?: boolean;
  size?: number;
  className?: string;
  isStreaming?: boolean;
  isTyping?: boolean;
}

export default function Logo({
  collapsed = false,
  size = 24,
  className = '',
  isStreaming = false,
}: LogoProps) {
  return (
    <div className={`flex items-center gap-2.5 select-none group/logo ${className}`}>
      {/* Sleek Interleaved Twisted Circle AI Emblem */}
      <div
        className="relative flex items-center justify-center flex-shrink-0 transition-transform duration-200 group-hover/logo:scale-105"
        style={{ width: size, height: size }}
      >
        <svg
          width={size}
          height={size}
          viewBox="0 0 24 24"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          className="overflow-visible"
        >
          <defs>
            <linearGradient id="twistGradA" x1="4" y1="4" x2="20" y2="20" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stopColor="#FFFFFF" />
              <stop offset="100%" stopColor="#94A3B8" />
            </linearGradient>
            <linearGradient id="twistGradB" x1="20" y1="4" x2="4" y2="20" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stopColor="#F8FAFC" />
              <stop offset="100%" stopColor="#64748B" />
            </linearGradient>
          </defs>

          {/* Interleaved Twisted Ring 1 */}
          <circle
            cx="12"
            cy="8.5"
            r="5.2"
            stroke="url(#twistGradA)"
            strokeWidth="1.8"
            strokeDasharray="24 8"
            className={isStreaming ? 'animate-spin' : ''}
            style={{ transformOrigin: '12px 12px' }}
          />

          {/* Interleaved Twisted Ring 2 */}
          <circle
            cx="8.8"
            cy="14.2"
            r="5.2"
            stroke="url(#twistGradB)"
            strokeWidth="1.8"
            strokeDasharray="24 8"
            className={isStreaming ? 'animate-spin' : ''}
            style={{ transformOrigin: '12px 12px', animationDirection: 'reverse' }}
          />

          {/* Interleaved Twisted Ring 3 */}
          <circle
            cx="15.2"
            cy="14.2"
            r="5.2"
            stroke="url(#twistGradA)"
            strokeWidth="1.8"
            strokeDasharray="24 8"
            className={isStreaming ? 'animate-spin' : ''}
            style={{ transformOrigin: '12px 12px' }}
          />

          {/* Glowing Center Core */}
          <circle
            cx="12"
            cy="12"
            r="1.8"
            fill="#FFFFFF"
          />
        </svg>
      </div>

      {!collapsed && (
        <div className="flex items-baseline gap-0.5 leading-none">
          <span className="font-semibold text-[15px] tracking-tight text-[#F2F2F2]">
            openChat
          </span>
        </div>
      )}
    </div>
  );
}
