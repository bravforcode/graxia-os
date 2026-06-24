export function SkeletonBlock({ className = "" }: { className?: string }) {
  return (
    <div
      className={`bg-slate-800/40 rounded-xl animate-pulse ${className}`}
      aria-hidden="true"
    />
  );
}

export function SkeletonText({
  lines = 3,
  className = "",
}: {
  lines?: number;
  className?: string;
}) {
  return (
    <div className={`space-y-2 ${className}`} aria-hidden="true">
      {Array.from({ length: lines }).map((_, i) => (
        <div
          key={i}
          className={`h-3 bg-slate-800/40 rounded animate-pulse ${
            i === lines - 1 ? "w-3/4" : "w-full"
          }`}
        />
      ))}
    </div>
  );
}

export function SkeletonProductCard() {
  return (
    <div className="bg-slate-900/40 border border-slate-800/60 rounded-3xl overflow-hidden">
      {/* Image */}
      <div className="h-44 bg-slate-800/40 animate-pulse" />
      {/* Content */}
      <div className="p-5 space-y-3">
        {/* Category badge */}
        <SkeletonBlock className="h-5 w-24 rounded-full" />
        {/* Title */}
        <SkeletonBlock className="h-5 w-4/5 rounded" />
        {/* Description */}
        <SkeletonText lines={2} />
        {/* Price + Sales */}
        <div className="flex items-end justify-between pt-3 border-t border-slate-800/60">
          <SkeletonBlock className="h-7 w-20 rounded" />
          <SkeletonBlock className="h-4 w-16 rounded" />
        </div>
      </div>
    </div>
  );
}

export function SkeletonProductGrid({ count = 8 }: { count?: number }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
      {Array.from({ length: count }).map((_, i) => (
        <SkeletonProductCard key={i} />
      ))}
    </div>
  );
}

/** Full-page product detail skeleton — used by StoreProductPage and PublicProductPage */
export function SkeletonProductDetail() {
  return (
    <div className="min-h-screen bg-slate-950 p-6">
      <div className="max-w-6xl mx-auto pt-20 space-y-16">
        {/* Hero grid skeleton */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-10">
          {/* Left column */}
          <div className="lg:col-span-7 space-y-5">
            <div className="flex gap-2">
              <SkeletonBlock className="h-6 w-32 rounded-full" />
              <SkeletonBlock className="h-6 w-20 rounded-full" />
            </div>
            <SkeletonBlock className="h-12 w-4/5 rounded" />
            <SkeletonBlock className="h-12 w-3/5 rounded" />
            <SkeletonBlock className="h-5 w-full rounded" />
            <SkeletonBlock className="h-5 w-3/4 rounded" />
            <div className="flex gap-4 pt-2">
              <SkeletonBlock className="h-4 w-28 rounded" />
              <SkeletonBlock className="h-4 w-20 rounded" />
              <SkeletonBlock className="h-4 w-24 rounded" />
            </div>
            <div className="space-y-2 pt-4">
              <SkeletonBlock className="h-4 w-32 rounded" />
              <div className="grid grid-cols-2 gap-2">
                {Array.from({ length: 6 }).map((_, i) => (
                  <SkeletonBlock key={i} className="h-4 rounded" />
                ))}
              </div>
            </div>
          </div>
          {/* Right column — checkout card */}
          <div className="lg:col-span-5">
            <div className="bg-slate-900/40 border border-slate-800 rounded-3xl p-6 space-y-5">
              <SkeletonBlock className="h-4 w-28 rounded" />
              <SkeletonBlock className="h-10 w-32 rounded" />
              <SkeletonBlock className="h-4 w-48 rounded" />
              <SkeletonBlock className="h-12 w-full rounded-xl" />
              <div className="space-y-2">
                {Array.from({ length: 4 }).map((_, i) => (
                  <SkeletonBlock key={i} className="h-4 rounded" />
                ))}
              </div>
              <SkeletonBlock className="h-16 w-full rounded-xl" />
            </div>
          </div>
        </div>
        {/* Testimonials skeleton */}
        <div className="space-y-4">
          <SkeletonBlock className="h-8 w-48 rounded" />
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="bg-slate-900/40 border border-slate-800/60 rounded-2xl p-5 space-y-3">
                <SkeletonBlock className="h-3 w-20 rounded" />
                <SkeletonText lines={3} />
                <div className="flex items-center gap-2 pt-1">
                  <SkeletonBlock className="h-8 w-8 rounded-full" />
                  <div className="space-y-1">
                    <SkeletonBlock className="h-3 w-20 rounded" />
                    <SkeletonBlock className="h-2 w-16 rounded" />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
