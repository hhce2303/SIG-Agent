import { BookOpen, Download, FileCheck2, Headphones, ListChecks } from 'lucide-react'
import AppShell from '../components/AppShell'

const resources = [
  { title: 'Call Opening Checklist', icon: Headphones, body: 'Confirm the exact location first, identify the incident, and determine immediate danger.' },
  { title: 'Critical Information Guide', icon: ListChecks, body: 'Location, callback number, people involved, weapons, injuries, descriptions, direction of travel.' },
  { title: 'Clear Communication', icon: FileCheck2, body: 'Use short factual sentences, answer the question asked, and clearly say when information is unknown.' },
]

export default function ResourcesPage() {
  const download = (title: string, body: string) => {
    const blob = new Blob([`# ${title}\n\n${body}\n`], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `${title.toLowerCase().replaceAll(' ', '-')}.md`
    anchor.click()
    URL.revokeObjectURL(url)
  }
  return <AppShell active="Resources"><div className="content-page"><div className="page-heading-row"><div><h1>Training Resources</h1><p>Practical references that can be saved for offline study.</p></div></div><div className="resource-grid">{resources.map(({ title, icon: Icon, body }) => <article className="panel resource-card" key={title}><Icon size={31} /><h2>{title}</h2><p>{body}</p><button className="secondary-button" onClick={() => download(title, body)}><Download size={17} />Download guide</button></article>)}</div><section className="panel resource-principles"><BookOpen size={25} /><div><h2>Training principle</h2><p>The simulator never reveals scenario facts during a call. Results and the complete transcript become available only after the session ends.</p></div></section></div></AppShell>
}
