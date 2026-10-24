const buttonBase =
  'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md px-3.5 py-2 text-sm font-semibold ' +
  'transition-colors disabled:cursor-not-allowed disabled:opacity-60'

export const buttonStyles = {
  primary: `${buttonBase} bg-ink text-page hover:bg-ink/85`,
  secondary: `${buttonBase} border border-line bg-surface text-ink hover:bg-surface-muted`,
  danger: `${buttonBase} border border-line bg-surface text-danger hover:bg-surface-muted`,
} as const
