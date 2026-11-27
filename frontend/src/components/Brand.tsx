export function BrandMark({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden>
      <rect width="32" height="32" rx="6" fill="#11182B" />
      <rect x="9" y="6" width="2" height="20" fill="#F3EFE6" />
      <rect x="14" y="10" width="11" height="7" fill="#F2B705" />
      <rect x="14" y="20" width="7" height="3" fill="#F3EFE6" />
    </svg>
  );
}

export function BrandName({ className = "" }: { className?: string }) {
  return (
    <span className={`inline-flex items-center gap-2 font-display text-3xl font-bold uppercase tracking-wide ${className}`}>
      <BrandMark />
      Sideline
    </span>
  );
}
