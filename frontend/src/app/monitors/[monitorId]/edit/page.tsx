import Link from 'next/link'

import { EditMonitorForm } from '@/app/monitors/edit-monitor-form'
import { authenticatedApiFetch } from '@/lib/auth'
import type { Monitor, Target } from '@/lib/monitoring'

import '../../monitors.css'

type EditMonitorPageProps = {
  params: Promise<{ monitorId: string }>
}

export default async function EditMonitorPage({ params }: EditMonitorPageProps) {
  const { monitorId } = await params
  const [monitor, targets] = await Promise.all([
    authenticatedApiFetch<Monitor>(`/monitoring/monitors/${monitorId}`),
    authenticatedApiFetch<Target[]>('/monitoring/targets'),
  ])

  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">Checks</span>
          <h1>Edit {monitor.name}</h1>
          <p>
            Change the target, schedule or native probe configuration while
            preserving the monitor&apos;s stable identity and historical data.
          </p>
        </div>
        <Link className="secondary" href="/monitors">
          Back to monitors
        </Link>
      </div>

      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Monitor configuration</h2>
            <p className="muted">
              Current revision: {monitor.revision}. Metadata-only edits do not
              create a new agent-facing revision.
            </p>
          </div>
        </div>
        <EditMonitorForm monitor={monitor} targets={targets} />
      </section>
    </>
  )
}
