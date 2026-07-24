interface LogoProps {
  collapsed?: boolean;
  size?: number;
  className?: string;
}

export default function Logo({ collapsed = false, size = 28, className = '' }: LogoProps) {
  return (
    <div className={`flex items-center gap-2.5 select-none group/logo ${className}`}>
      {/* Bot icon — inverted to white for dark theme */}
      <img
        src="/bot-logo.png"
        alt="Omni AI"
        width={size}
        height={size}
        aria-hidden={collapsed}
        className="flex-shrink-0 transition-transform duration-300 group-hover/logo:scale-105"
        style={{
          filter: 'invert(1) brightness(1.8)',
          width: size,
          height: size,
          objectFit: 'contain',
        }}
      />

      {/* Wordmark — hidden when collapsed */}
      {!collapsed && (
        <div className="flex items-baseline gap-0.5 leading-none">
          <span className="font-bold text-[15px] tracking-tight text-foreground">
            Omni
          </span>
          <span className="text-[11px] font-semibold text-foreground-3 ml-0.5">AI</span>
        </div>
      )}
    </div>
  );
}
