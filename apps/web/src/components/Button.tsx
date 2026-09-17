import type { ButtonHTMLAttributes, ReactNode } from 'react'
import './Button.css'

type Variant = 'primary' | 'secondary' | 'danger'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  children: ReactNode
}

export function Button({ variant = 'primary', className = '', ...props }: ButtonProps) {
  const variantClass = props.disabled ? 'btn-disabled' : `btn-${variant}`
  return <button className={`btn button ${variantClass} ${className}`} {...props} />
}
