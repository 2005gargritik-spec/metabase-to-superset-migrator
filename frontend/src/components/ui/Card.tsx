import React from 'react'

export type CardVariant = 'default' | 'metric' | 'elevated' | 'glass'

type CardElement = 'section' | 'article' | 'div' | 'form'

export interface CardProps {
  children: React.ReactNode
  className?: string
  variant?: CardVariant
  hover?: boolean
  as?: CardElement
  onSubmit?: React.FormEventHandler<HTMLFormElement>
}

export function Card({
  children,
  className = '',
  variant = 'default',
  hover = false,
  as: Component = 'section',
  onSubmit,
}: CardProps) {
  const classes = [
    'card',
    `card--${variant}`,
    hover ? 'card--hover' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ')

  if (Component === 'form') {
    return (
      <form className={classes} onSubmit={onSubmit}>
        {children}
      </form>
    )
  }

  const Tag = Component
  return <Tag className={classes}>{children}</Tag>
}
