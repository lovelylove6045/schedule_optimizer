import { Toaster as SonnerToaster } from "sonner"

/**
 * App-wide toast host. Styled to match the frosted-glass surfaces in index.css
 * (`.glass-raised`) rather than sonner's default opaque card, and given explicit
 * per-severity accent borders so success/error/warning read at a glance.
 */
export function Toaster() {
  return (
    <SonnerToaster
      position="top-right"
      closeButton
      toastOptions={{
        classNames: {
          toast: "glass-raised !rounded-xl !text-foreground !font-sans !gap-3",
          title: "!text-sm !font-semibold",
          description: "!text-xs !text-muted-foreground",
          actionButton: "!bg-primary !text-primary-foreground !rounded-md",
          cancelButton: "!bg-secondary !text-secondary-foreground !rounded-md",
          closeButton: "glass-raised !text-foreground",
          success: "!border-success/40",
          error: "!border-destructive/40",
          warning: "!border-warning/40",
          info: "!border-primary/30",
        },
      }}
    />
  )
}
