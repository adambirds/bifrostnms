'use client'

import { useActionState, useState } from 'react'

import {
  createMonitorAction,
  initialMonitorFormState,
} from '@/app/monitors/actions'
import type { ProbeType, Target } from '@/lib/monitoring'

const probeLabels: Record<ProbeType, string> = {
  icmp: 'ICMP',
  http: 'HTTP / HTTPS',
  tcp: 'TCP',
  dns: 'DNS',
  tls: 'TLS certificate',
}

function AddressFamilyField() {
  return (
    <label>
      Address family
      <select name="address_family" defaultValue="auto">
        <option value="auto">Automatic</option>
        <option value="ipv4">IPv4</option>
        <option value="ipv6">IPv6</option>
      </select>
    </label>
  )
}

function IcmpFields() {
  return (
    <div className="form-grid monitor-probe-fields">
      <label>
        Packets
        <input name="packet_count" type="number" min={1} max={100} defaultValue={20} required />
      </label>
      <label>
        Packet interval (ms)
        <input name="packet_interval_ms" type="number" min={10} max={1000} defaultValue={50} required />
      </label>
      <label>
        Payload size (bytes)
        <input name="payload_size_bytes" type="number" min={0} max={1400} defaultValue={56} required />
      </label>
      <AddressFamilyField />
      <label>
        Maximum packet loss (%)
        <input name="maximum_packet_loss_percent" type="number" min={0} max={100} step="0.1" />
      </label>
      <label>
        Maximum average RTT (ms)
        <input name="maximum_average_rtt_ms" type="number" min={0} step="0.1" />
      </label>
    </div>
  )
}

function HttpFields() {
  return (
    <div className="form-grid monitor-probe-fields">
      <label>
        Scheme
        <select name="scheme" defaultValue="https">
          <option value="https">HTTPS</option>
          <option value="http">HTTP</option>
        </select>
      </label>
      <label>
        Port (optional)
        <input name="port" type="number" min={1} max={65535} />
      </label>
      <label>
        Path
        <input name="path" defaultValue="/" required />
      </label>
      <label>
        Method
        <select name="method" defaultValue="GET">
          <option value="GET">GET</option>
          <option value="HEAD">HEAD</option>
        </select>
      </label>
      <label>
        Host header (optional)
        <input name="host_header" />
      </label>
      <AddressFamilyField />
      <label>
        Expected status codes
        <input name="expected_status_codes" defaultValue="200,201,202,204,301,302,303,307,308" />
      </label>
      <label>
        Maximum redirects
        <input name="maximum_redirects" type="number" min={0} max={10} defaultValue={5} required />
      </label>
      <label>
        Maximum response bytes
        <input name="maximum_response_bytes" type="number" min={1} max={4194304} defaultValue={1048576} required />
      </label>
      <label className="checkbox-label">
        <input name="follow_redirects" type="checkbox" defaultChecked />
        Follow redirects
      </label>
    </div>
  )
}

function TcpFields() {
  return (
    <div className="form-grid monitor-probe-fields">
      <label>
        Port
        <input name="port" type="number" min={1} max={65535} required />
      </label>
      <AddressFamilyField />
    </div>
  )
}

function DnsFields() {
  return (
    <div className="form-grid monitor-probe-fields">
      <label>
        Resolver mode
        <select name="resolver_mode" defaultValue="system">
          <option value="system">System resolver</option>
          <option value="explicit">Explicit resolver</option>
        </select>
      </label>
      <label>
        Resolver address
        <input name="resolver_address" placeholder="1.1.1.1" />
      </label>
      <label>
        Resolver port
        <input name="resolver_port" type="number" min={1} max={65535} defaultValue={53} required />
      </label>
      <label>
        Transport
        <select name="transport" defaultValue="udp_with_tcp_fallback">
          <option value="udp_with_tcp_fallback">UDP with TCP fallback</option>
          <option value="tcp">TCP</option>
        </select>
      </label>
      <label>
        Query name (optional)
        <input name="query_name" placeholder="example.com" />
      </label>
      <label>
        Query type
        <select name="query_type" defaultValue="A">
          {['A', 'AAAA', 'CNAME', 'MX', 'NS', 'TXT', 'PTR'].map(value => (
            <option key={value} value={value}>{value}</option>
          ))}
        </select>
      </label>
      <label>
        Expected response codes
        <input name="expected_response_codes" defaultValue="NOERROR" />
      </label>
      <label className="checkbox-label">
        <input name="recursion_desired" type="checkbox" defaultChecked />
        Recursion desired
      </label>
    </div>
  )
}

function TlsFields() {
  return (
    <div className="form-grid monitor-probe-fields">
      <label>
        Port
        <input name="port" type="number" min={1} max={65535} defaultValue={443} required />
      </label>
      <label>
        Server name (optional)
        <input name="server_name" placeholder="example.com" />
      </label>
      <AddressFamilyField />
      <label>
        Minimum TLS version
        <select name="minimum_tls_version" defaultValue="1.2">
          <option value="1.2">TLS 1.2</option>
          <option value="1.3">TLS 1.3</option>
        </select>
      </label>
      <label>
        Expiry warning (days)
        <input name="expiry_warning_days" type="number" min={0} max={3650} defaultValue={30} required />
      </label>
    </div>
  )
}

export function MonitorForm({ targets }: { targets: Target[] }) {
  const [probeType, setProbeType] = useState<ProbeType>('icmp')
  const [state, formAction, pending] = useActionState(
    createMonitorAction,
    initialMonitorFormState,
  )

  return (
    <form className="resource-form" action={formAction}>
      <div className="form-grid">
        <label>
          Name
          <input name="name" required maxLength={200} />
        </label>
        <label>
          Target
          <select name="target_id" defaultValue="" required>
            <option value="" disabled>Select target</option>
            {targets.map(target => (
              <option key={target.id} value={target.id}>{target.name} — {target.address}</option>
            ))}
          </select>
        </label>
        <label>
          Probe type
          <select
            name="probe_type"
            value={probeType}
            onChange={event => setProbeType(event.target.value as ProbeType)}
          >
            {(Object.keys(probeLabels) as ProbeType[]).map(type => (
              <option key={type} value={type}>{probeLabels[type]}</option>
            ))}
          </select>
        </label>
        <label>
          Interval (seconds)
          <input name="interval_seconds" type="number" min={1} defaultValue={60} required />
        </label>
        <label>
          Timeout (seconds)
          <input name="timeout_seconds" type="number" min={1} defaultValue={10} required />
        </label>
      </div>
      <label>
        Description
        <textarea name="description" rows={2} />
      </label>

      <div className="probe-configuration">
        <div>
          <span className="eyebrow">Probe configuration</span>
          <h3>{probeLabels[probeType]}</h3>
        </div>
        {probeType === 'icmp' ? <IcmpFields /> : null}
        {probeType === 'http' ? <HttpFields /> : null}
        {probeType === 'tcp' ? <TcpFields /> : null}
        {probeType === 'dns' ? <DnsFields /> : null}
        {probeType === 'tls' ? <TlsFields /> : null}
      </div>

      {state.error ? <p className="form-error">{state.error}</p> : null}
      {state.success ? <p className="form-success">{state.success}</p> : null}
      <button type="submit" disabled={pending || targets.length === 0}>
        {pending ? 'Creating…' : 'Create monitor'}
      </button>
    </form>
  )
}
