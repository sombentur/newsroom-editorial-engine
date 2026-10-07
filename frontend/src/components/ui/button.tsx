import { isValidElement } from "react"
import { Button as ButtonPrimitive } from "@base-ui/react/button"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

// Navy primary, white outline. Hover adds the amber accent (a fine ring or border); focus is a navy edge with an
// amber halo. Heights are one step roomier than the stock set for comfortable touch targets.
const buttonVariants = cva(
  "group/button inline-flex shrink-0 items-center justify-center rounded-lg border border-transparent bg-clip-padding text-sm font-medium whitespace-nowrap transition-all duration-200 outline-none select-none focus-visible:border-navy-600 focus-visible:ring-3 focus-visible:ring-amber-400/50 active:not-aria-[haspopup]:translate-y-px disabled:pointer-events-none disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 dark:aria-invalid:border-destructive/50 dark:aria-invalid:ring-destructive/40 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default: "bg-gradient-to-b from-navy-700 to-navy-800 text-[#fdfbf6] shadow-[0_6px_16px_-8px_rgb(1_27_75/0.6),inset_0_1px_0_rgb(255_255_255/0.16)] hover:from-navy-600 hover:to-navy-800 hover:shadow-[0_0_0_1px_rgb(245_157_28/0.7),0_10px_22px_-10px_rgb(1_27_75/0.7),inset_0_1px_0_rgb(255_255_255/0.2)]",
        outline:
          "border-slate-300 bg-white text-slate-800 shadow-[0_1px_2px_rgb(1_27_75/0.05)] hover:border-amber-400 hover:bg-amber-50/70 hover:text-navy-900 aria-expanded:border-amber-400 aria-expanded:bg-amber-50/70 aria-expanded:text-navy-900",
        secondary:
          "bg-secondary text-secondary-foreground hover:bg-[color-mix(in_oklch,var(--secondary),var(--foreground)_6%)] aria-expanded:bg-secondary aria-expanded:text-secondary-foreground",
        ghost:
          "hover:bg-amber-50/80 hover:text-navy-900 aria-expanded:bg-amber-50/80 aria-expanded:text-navy-900",
        destructive:
          "border-rose-200 bg-rose-50 text-rose-800 hover:border-rose-400 hover:bg-rose-100 focus-visible:border-destructive/40 focus-visible:ring-destructive/20",
        link: "text-navy-700 underline-offset-4 decoration-amber-400 hover:underline",
      },
      size: {
        default:
          "h-9 gap-1.5 px-3.5 has-data-[icon=inline-end]:pr-2.5 has-data-[icon=inline-start]:pl-2.5",
        xs: "h-7 gap-1 rounded-[min(var(--radius-md),10px)] px-2.5 text-xs in-data-[slot=button-group]:rounded-lg has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 [&_svg:not([class*='size-'])]:size-3",
        sm: "h-8 gap-1.5 rounded-[min(var(--radius-md),12px)] px-3 text-[0.8125rem] in-data-[slot=button-group]:rounded-lg has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2 [&_svg:not([class*='size-'])]:size-3.5",
        lg: "h-10 gap-2 px-4 text-[0.9375rem] has-data-[icon=inline-end]:pr-3 has-data-[icon=inline-start]:pl-3",
        icon: "size-9",
        "icon-xs":
          "size-7 rounded-[min(var(--radius-md),10px)] in-data-[slot=button-group]:rounded-lg [&_svg:not([class*='size-'])]:size-3",
        "icon-sm":
          "size-8 rounded-[min(var(--radius-md),12px)] in-data-[slot=button-group]:rounded-lg",
        "icon-lg": "size-10",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Button({
  className,
  variant = "default",
  size = "default",
  nativeButton,
  render,
  ...props
}: ButtonPrimitive.Props & VariantProps<typeof buttonVariants>) {
  return (
    <ButtonPrimitive
      data-slot="button"
      render={render}
      // Native unless render swaps in a non-<button> element (e.g. <Link/>).
      nativeButton={
        nativeButton ??
        (render == null || (isValidElement(render) && render.type === "button"))
      }
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
