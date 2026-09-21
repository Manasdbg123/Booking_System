"use client";

/**
 * Deterministic generated artwork per event.
 *
 * The seed dataset has no real poster images, and an emoji placeholder on
 * every card made them all look identical. Hashing the title into a hue
 * gives each event a stable, distinct piece of art that survives reloads
 * and doesn't need any assets.
 */

// Hues are deliberately confined to an indigo → violet → magenta band
// (rather than the full wheel) so every event still looks distinct while
// staying inside the product's single-accent palette. A free-for-all hue
// produced olive and teal cards that read as a different brand.
const HUE_START = 232;
const HUE_RANGE = 96;

function hashHue(text: string): number {
  let hash = 0;
  for (let i = 0; i < text.length; i++) hash = (hash * 31 + text.charCodeAt(i)) % 9973;
  return HUE_START + (hash % HUE_RANGE);
}

export function EventPoster({ title, className, tall = false }: { title: string; className?: string; tall?: boolean }) {
  const hue = hashHue(title);
  const hue2 = HUE_START + ((hue - HUE_START + 40) % HUE_RANGE);
  const initials = title
    .replace(/[^\p{L}\p{N} ]/gu, "")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase())
    .join("");

  // Concentric arcs suggesting a stage/soundwave, angled for a bit of motion.
  const rings = [0.35, 0.52, 0.69, 0.86];

  return (
    <div className={className} aria-hidden>
      <svg viewBox={`0 0 400 ${tall ? 300 : 200}`} className="h-full w-full" preserveAspectRatio="xMidYMid slice">
        <defs>
          <linearGradient id={`g-${hue}`} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor={`hsl(${hue} 58% 38%)`} />
            <stop offset="55%" stopColor={`hsl(${hue2} 52% 22%)`} />
            <stop offset="100%" stopColor="#12121b" />
          </linearGradient>
          <radialGradient id={`spot-${hue}`} cx="50%" cy="0%" r="85%">
            <stop offset="0%" stopColor="#ffffff" stopOpacity="0.30" />
            <stop offset="100%" stopColor="#ffffff" stopOpacity="0" />
          </radialGradient>
        </defs>
        <rect width="400" height={tall ? 300 : 200} fill={`url(#g-${hue})`} />
        {rings.map((r, i) => (
          <ellipse
            key={i}
            cx="200"
            cy={tall ? 300 : 210}
            rx={200 * r * 1.5}
            ry={(tall ? 300 : 200) * r}
            fill="none"
            stroke="#ffffff"
            strokeOpacity={0.16 - i * 0.03}
            strokeWidth="1.2"
          />
        ))}
        <rect width="400" height={tall ? 300 : 200} fill={`url(#spot-${hue})`} />
        <text
          x="200"
          y={tall ? 165 : 112}
          textAnchor="middle"
          fill="#ffffff"
          fillOpacity="0.9"
          style={{ fontSize: tall ? 74 : 56, fontWeight: 700, letterSpacing: 2 }}
        >
          {initials}
        </text>
      </svg>
    </div>
  );
}
