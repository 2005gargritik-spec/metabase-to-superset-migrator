import React from 'react'

export type ButtonVariant =
  | 'primary'
  | 'secondary'
  | 'outline'
  | 'ghost'
  | 'danger'
  | 'success'

export type ButtonSize = 'default' | 'compact'

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  fullWidth?: boolean
  active?: boolean
  nav?: boolean
}

export function Button({
  variant = 'secondary',
  size = 'default',
  fullWidth = false,
  active = false,
  nav = false,
  className = '',
  children,
  ...props
}: ButtonProps) {
  const classes = [
    'btn',
    `btn--${variant}`,
    size === 'compact' ? 'btn--compact' : '',
    fullWidth ? 'btn--full' : '',
    active ? 'btn--active' : '',
    nav ? 'btn--nav' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <button className={classes} {...props}>
      {children}
    </button>
  )
}
