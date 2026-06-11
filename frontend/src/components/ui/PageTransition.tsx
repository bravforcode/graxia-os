import { useLocation } from "react-router-dom";
import { type ReactNode } from "react";

interface PageTransitionProps {
  children: ReactNode;
}

/**
 * Wraps routed pages with a smooth enter animation.
 * Uses key={pathname} to re-mount and re-trigger the CSS animation on navigation.
 */
export function PageTransition({ children }: PageTransitionProps) {
  const location = useLocation();
  return (
    <div
      key={location.pathname}
      className="animate-page-enter will-change-[opacity,transform]"
    >
      {children}
    </div>
  );
}
