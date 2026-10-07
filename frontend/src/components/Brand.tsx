// Placeholder logo. Replace the two files in src/assets/brand (and the icons in public/) with your own; keep the
// proportions (1200×258 and 512×302) or adjust the width/height below.
import logoUrl from "@/assets/brand/newsroom-logo.webp";
import markUrl from "@/assets/brand/newsroom-mark.webp";
import { cn } from "@/lib/utils";

export const BRAND_NAME = "News Room Editorial Engine";

/** The full logo: icon mark, "News Room" and "Editorial Engine". Set the width with a class; height follows. */
export function BrandLogo({ className, priority }: { className?: string; priority?: boolean }) {
  return (
    <img
      src={logoUrl} width={1200} height={258} alt="News Room — Editorial Engine"
      decoding={priority ? "sync" : "async"} fetchPriority={priority ? "high" : "auto"} draggable={false}
      className={cn("h-auto max-w-full select-none", className)}
    />
  );
}

/** The icon mark alone, for places too small for the wordmark. Decorative: pair it with visible or sr-only text. */
export function BrandMark({ className }: { className?: string }) {
  return (
    <img
      src={markUrl} width={512} height={302} alt="" aria-hidden="true" decoding="async" draggable={false}
      className={cn("h-auto max-w-full select-none", className)}
    />
  );
}
