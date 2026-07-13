

interface LogoProps {
  collapsed?: boolean;
  size?: number;
  className?: string;
}

export default function Logo({ collapsed = false, size = 28, className = '' }: LogoProps) {
  return (
    <div className={`flex items-center gap-2.5 select-none ${className}`}>
      {/* SVG Mark */}
      <svg
        width={size}
        height={size}
        viewBox="0 0 32 32"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="flex-shrink-0"
        aria-hidden="true"
      >
        {/* Outer hexagon ring */}
        <path
          d="M16 2L28 9V23L16 30L4 23V9L16 2Z"
          stroke="url(#logo-grad)"
          strokeWidth="1.5"
          fill="none"
          strokeLinejoin="round"
        />
        {/* Inner solid diamond */}
        <path
          d="M16 9L22 16L16 23L10 16L16 9Z"
          fill="url(#logo-grad)"
          opacity="0.9"
        />
        {/* Center dot */}
        <circle cx="16" cy="16" r="2" fill="white" opacity="0.9" />
        <defs>
          <linearGradient id="logo-grad" x1="4" y1="2" x2="28" y2="30" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#ffffff" />
            <stop offset="100%" stopColor="#8a8a93" />
          </linearGradient>
        </defs>
      </svg>

      {/* Wordmark – hidden when collapsed */}
      {!collapsed && (
        <span className="font-semibold text-[15px] tracking-tight text-foreground leading-none">
          Omni
        </span>
      )}
    </div>
  );
}
