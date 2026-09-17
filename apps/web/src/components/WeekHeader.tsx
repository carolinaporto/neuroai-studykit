import './WeekHeader.css'

export function WeekHeader({ week, title, meta }: { week: number; title: string; meta: string }) {
  return (
    <div className="wh">
      <div className="wh-row">
        <span className="wh-week tag">WK {String(week).padStart(2, '0')}</span>
        <div className="wh-text">
          <div className="h2">{title}</div>
          <div className="caption">{meta}</div>
        </div>
      </div>
      <div className="wh-rule" />
    </div>
  )
}
