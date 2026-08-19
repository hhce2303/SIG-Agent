export default function ScoreRing({ score, size = 130 }: { score: number; size?: number }) {
  const angle = `${Math.max(0, Math.min(100, score)) * 3.6}deg`
  return (
    <div
      className="score-ring"
      style={{ width: size, height: size, background: `conic-gradient(var(--primary) ${angle}, var(--track) 0deg)` }}
    >
      <div className="score-ring-inner">
        <strong>{score}</strong>
        <span>/100</span>
      </div>
    </div>
  )
}
