// Smooth animation utilities — use these consistently across all pages

// CSS class strings for consistent animations
export const ANIMATIONS = {
  // Page-level fade-in
  pageEnter: "animate-fade-in",
  pageEnterUp: "animate-fade-in-up",

  // Card hover effects
  cardHover: "transition-all duration-300 ease-out hover:-translate-y-1 hover:shadow-card-hover",
  cardHoverGlow: "transition-all duration-300 ease-out hover:-translate-y-1 hover:shadow-glow-sm hover:border-indigo-500/30",

  // Button press & hover
  buttonPress: "active:scale-[0.97] active:transition-transform active:duration-100",
  buttonHover: "transition-all duration-200 ease-out hover:-translate-y-0.5 hover:shadow-glow-md",

  // Icon animations
  iconBounce: "group-hover:scale-110 transition-transform duration-300",
  iconSpin: "group-hover:rotate-12 transition-transform duration-300",
  iconSlide: "group-hover:translate-x-1 transition-transform duration-200",

  // Stagger children (apply to parent, children get animationDelay via style)
  staggerParent: "",

  // Focus ring
  focusRing: "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950",

  // Shimmer loading effect
  shimmer: "bg-shimmer-gradient bg-[length:200%_100%] animate-shimmer",

  // Floating animation
  float: "animate-float",

  // Glow pulse
  glowPulse: "animate-glow",

  // Smooth underline for links
  underlineHover: "relative after:absolute after:bottom-0 after:left-0 after:w-0 after:h-[2px] after:bg-indigo-400 after:transition-all after:duration-300 hover:after:w-full",
} as const;

// Generate stagger delay style for children
export function staggerDelay(index: number, baseMs = 60): React.CSSProperties {
  return { animationDelay: `${index * baseMs}ms` };
}
