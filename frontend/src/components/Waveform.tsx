import { motion } from 'motion/react'

const heights = [10,14,9,16,22,13,18,28,34,20,44,32,58,26,46,64,82,42,27,39,54,31,66,49,30,42,58,71,40,36,28,51,64,45,33,22,15,10]

export default function Waveform({ active = true }: { active?: boolean }) {
  return (
    <div className="waveform" aria-label={active ? 'Audio active' : 'Audio idle'}>
      {heights.map((height, i) => (
        <motion.span
          key={i}
          className="wave-bar"
          animate={active ? { height: [Math.max(8, height * .45), height, Math.max(8, height * .55)] } : { height: 7 }}
          transition={{ duration: .7 + (i % 5) * .08, repeat: Infinity, repeatType: 'mirror', delay: i * .014 }}
        />
      ))}
    </div>
  )
}
