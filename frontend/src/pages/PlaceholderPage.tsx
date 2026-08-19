import AppShell from '../components/AppShell'

export default function PlaceholderPage({ title, subtitle }: { title: string; subtitle: string }) {
  return <AppShell active={title}><div className="placeholder panel"><h1>{title}</h1><p>{subtitle}</p><span>This area is ready for the next SIG Agent module.</span></div></AppShell>
}
