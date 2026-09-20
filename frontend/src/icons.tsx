interface IconProps {
  className?: string
}

const base = {
  width: 20,
  height: 20,
  viewBox: '0 0 20 20',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.6,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
}

export function IconShieldCheck({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden>
      <path d="M10 2.2 16.8 4.6v4.6c0 5-2.9 7.9-6.8 8.6-3.9-.7-6.8-3.6-6.8-8.6V4.6z" />
      <path d="M6.8 9.9l2.2 2.2L13.5 7.6" />
    </svg>
  )
}

export function IconTriangleAlert({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden>
      <path d="M10 3.2 17.5 16.3H2.5z" />
      <path d="M10 8.3v3.4" />
      <circle cx="10" cy="14.1" r="0.15" fill="currentColor" stroke="none" />
    </svg>
  )
}

export function IconOctagonStop({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden>
      <path d="M6.3 2.5h7.4l4.8 4.8v7.4l-4.8 4.8H6.3l-4.8-4.8V7.3z" />
      <path d="M7 7l6 6M13 7l-6 6" />
    </svg>
  )
}

export function IconArrowLeft({ className }: IconProps) {
  return (
    <svg {...base} width={16} height={16} viewBox="0 0 16 16" className={className} aria-hidden>
      <path d="M13 8H3M6.5 4 3 8l3.5 4" />
    </svg>
  )
}

export function IconArrowRight({ className }: IconProps) {
  return (
    <svg {...base} width={16} height={16} viewBox="0 0 16 16" className={className} aria-hidden>
      <path d="M3 8h10M9.5 4 13 8l-3.5 4" />
    </svg>
  )
}

export function IconUpload({ className }: IconProps) {
  return (
    <svg {...base} width={16} height={16} viewBox="0 0 16 16" className={className} aria-hidden>
      <path d="M8 10.5V2.5M5 5.3 8 2.2l3 3.1" />
      <path d="M2.5 10.5v2a1.5 1.5 0 0 0 1.5 1.5h8a1.5 1.5 0 0 0 1.5-1.5v-2" />
    </svg>
  )
}
