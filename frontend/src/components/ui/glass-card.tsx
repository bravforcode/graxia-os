import React from "react";
import { motion, HTMLMotionProps } from "framer-motion";
import { cn } from "@/lib/utils";

interface GlassCardProps extends HTMLMotionProps<"div"> {
  children: React.ReactNode;
  className?: string;
  intensity?: "low" | "medium" | "high";
}

export const GlassCard = React.forwardRef<HTMLDivElement, GlassCardProps>(
  ({ children, className, intensity = "medium", ...props }, ref) => {
    const intensityClasses = {
      low: "bg-zinc-900/20 backdrop-blur-md",
      medium: "bg-zinc-900/40 backdrop-blur-xl",
      high: "bg-zinc-900/60 backdrop-blur-2xl",
    };

    return (
      <motion.div
        ref={ref}
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className={cn(
          "rounded-2xl border border-white/10 shadow-2xl overflow-hidden",
          intensityClasses[intensity],
          className
        )}
        {...props}
      >
        {children}
      </motion.div>
    );
  }
);
GlassCard.displayName = "GlassCard";
