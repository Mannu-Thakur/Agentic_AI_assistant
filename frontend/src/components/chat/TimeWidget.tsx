import React, { useState, useEffect } from 'react';

interface TimeWidgetProps {
  location?: string;
}

function getLocationLabel(): { city: string; region: string; country: string } {
  try {
    const raw = localStorage.getItem('omni_user_location');
    if (raw) {
      // Format: "City, Region, Country" or similar
      const parts = raw.split(',').map((s) => s.trim());
      return {
        city: parts[0] || 'Your Location',
        region: parts[1] || '',
        country: parts[2] || '',
      };
    }
  } catch (_) {}
  return { city: 'Your Location', region: '', country: '' };
}

function formatDigital(d: Date) {
  return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', hour12: true });
}

function getDayBadge(d: Date) {
  const now = new Date();
  const isToday =
    d.getDate() === now.getDate() &&
    d.getMonth() === now.getMonth() &&
    d.getFullYear() === now.getFullYear();
  return isToday ? 'Today' : d.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' });
}

function getOffset() {
  const off = -new Date().getTimezoneOffset(); // minutes
  const h = Math.floor(Math.abs(off) / 60);
  const m = Math.abs(off) % 60;
  const sign = off >= 0 ? '+' : '-';
  return `${sign}${h}${m ? `:${String(m).padStart(2, '0')}` : ''}hrs`;
}

// Draw tick marks on SVG clock face
function ClockFace({ size }: { size: number }) {
  const cx = size / 2;
  const cy = size / 2;
  const r = size / 2;
  const ticks = Array.from({ length: 60 }, (_, i) => {
    const angle = (i * 6 - 90) * (Math.PI / 180);
    const isHour = i % 5 === 0;
    const inner = r - (isHour ? 9 : 5);
    const outer = r - 2;
    return {
      x1: cx + inner * Math.cos(angle),
      y1: cy + inner * Math.sin(angle),
      x2: cx + outer * Math.cos(angle),
      y2: cy + outer * Math.sin(angle),
      isHour,
    };
  });
  return (
    <>
      {ticks.map((t, i) => (
        <line
          key={i}
          x1={t.x1} y1={t.y1}
          x2={t.x2} y2={t.y2}
          stroke={t.isHour ? '#6b7280' : '#374151'}
          strokeWidth={t.isHour ? 2 : 1}
          strokeLinecap="round"
        />
      ))}
    </>
  );
}

export const TimeWidget: React.FC<TimeWidgetProps> = () => {
  const [now, setNow] = useState(new Date());
  const loc = getLocationLabel();

  useEffect(() => {
    const timer = setInterval(() => {
      setNow(new Date());
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  const SIZE = 96;
  const CX = SIZE / 2;
  const CY = SIZE / 2;

  const h = now.getHours() % 12;
  const m = now.getMinutes();
  const s = now.getSeconds();

  const hourDeg   = h * 30 + m * 0.5 + s * (0.5 / 60);
  const minuteDeg = m * 6 + s * 0.1;
  const secondDeg = s * 6;

  const handAngle = (deg: number) => (deg - 90) * (Math.PI / 180);

  function handCoords(deg: number, length: number) {
    const angle = handAngle(deg);
    return {
      x2: CX + length * Math.cos(angle),
      y2: CY + length * Math.sin(angle),
    };
  }

  const hourHand   = handCoords(hourDeg, 22);
  const minuteHand = handCoords(minuteDeg, 30);
  const secondHand = handCoords(secondDeg, 34);

  const locationText = [loc.city, loc.region, loc.country].filter(Boolean).join(', ');

  return (
    <div className="my-3 block">
      <div
        className="inline-flex items-center gap-5 bg-[#1c1c1e] border border-white/[0.08] rounded-2xl px-5 py-4 shadow-2xl hover:border-white/[0.14] transition-all duration-300"
        style={{ minWidth: 260, maxWidth: 340 }}
      >
        {/* Left: Digital info */}
        <div className="flex flex-col gap-0.5 flex-1 min-w-0">
          <div className="text-[28px] font-bold text-white tracking-tight leading-none tabular-nums">
            {formatDigital(now)}
          </div>
          <div className="text-[13px] text-zinc-300 font-medium mt-1.5 truncate">
            {locationText || 'Your Location'}
          </div>
          <div className="text-[11px] text-zinc-500 font-normal mt-0.5">
            {getDayBadge(now)}, {getOffset()}
          </div>
        </div>

        {/* Right: Analog SVG Clock */}
        <svg
          width={SIZE}
          height={SIZE}
          viewBox={`0 0 ${SIZE} ${SIZE}`}
          className="flex-shrink-0 drop-shadow-lg"
        >
          {/* Clock face circle */}
          <circle cx={CX} cy={CY} r={SIZE / 2 - 1} fill="#111113" stroke="#2d2d30" strokeWidth="1.5" />

          {/* Tick marks */}
          <ClockFace size={SIZE} />

          {/* Hour hand */}
          <line
            x1={CX} y1={CY}
            x2={hourHand.x2} y2={hourHand.y2}
            stroke="white" strokeWidth="3" strokeLinecap="round"
          />

          {/* Minute hand */}
          <line
            x1={CX} y1={CY}
            x2={minuteHand.x2} y2={minuteHand.y2}
            stroke="#d1d5db" strokeWidth="2" strokeLinecap="round"
          />

          {/* Second hand — red with tail */}
          <line
            x1={CX + 8 * Math.cos(handAngle(secondDeg + 180))}
            y1={CY + 8 * Math.sin(handAngle(secondDeg + 180))}
            x2={secondHand.x2} y2={secondHand.y2}
            stroke="#ef4444" strokeWidth="1.5" strokeLinecap="round"
            style={{ transition: s === 0 ? 'none' : 'all 0.25s cubic-bezier(0.4,2.5,0.6,1)' }}
          />

          {/* Center pin */}
          <circle cx={CX} cy={CY} r={3.5} fill="#ef4444" />
          <circle cx={CX} cy={CY} r={1.5} fill="white" />
        </svg>
      </div>
    </div>
  );
};
