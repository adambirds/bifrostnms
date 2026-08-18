'use client'

import { useState } from 'react'

import type { Monitor, ProbeType, Target } from '@/lib/monitoring'

const probeLabels: Record<ProbeType, string> = {
  icmp: 'ICMP',
  http: 'HTTP / HTTPS',
  tcp: 'TCP',
  dns: 'DNS',
  tls: 'TLS certificate',
}

function configString(
  monitor: Monitor | null,
  key: string,
  fallback: string,
): string {
  const value = monitor?.configuration[key]
  return typeof value === 'string' ? value : fallback
}

function configNumber(
  monitor: Monitor | null,
  key: string,
  fallback: number,
): number {
  const value = monitor?.configuration[key]
  return typeof value === 'number' ? value : fallback
}

function optionalConfigNumber(
  monitor: Monitor | null,
  key: string,
): number | undefined {
  const value = monitor?.configuration[key]
  return typeof value === 'number' ? value : undefined
}

function configBoolean(
  monitor: Monitor | null,
  key: string,
  fallback: boolean,
): boolean {
  const value = monitor?.configuration[key]
  return typeof value === 'boolean' ? value : fallback
}

function configArray(monitor: Monitor | null, key: string, fallback: string): string {
  const value = monitor?.configuration[key]
  if (!Array.isArray(value)) return fallback
  return value.map((item) => String(item)).join(',')
}

function AddressFamilyField({ monitor }: { monitor: Monitor | null }) {
  return (
    <label>
      Address family
      <select
        name="address_family"
        defaultValue={configString(monitor, 'address_family', 'auto')}
      >
        <option value="auto">Automatic</option>
        <option value="ipv4">IPv4</option>
        <option value="ipv6">IPv6</option>
      </select>
    </label>
  )
}

function IcmpFields({ monitor }: { monitor: Monitor | null }) {
  return (
    <div className="form-grid monitor-probe-fields">
      <label>
        Packets
        <input
          name="packet_count"
          type="number"
          min={1}
          max={100}
          defaultValue={configNumber(monitor, 'packet_count', 20)}
          required
        />
      </label>
      <label>
        Packet interval (ms)
        <input
          name="packet_interval_ms"
          type="number"
          min={10}
          max={1000}
          defaultValue={configNumber(monitor, 'packet_interval_ms', 50)}
          required
        />
      </label>
      <label>
        Payload size (bytes)
        <input
          name="payload_size_bytes"
          type="number"
          min={0}
          max={1400}
          defaultValue={configNumber(monitor, 'payload_size_bytes', 56)}
          required
        />
      </label>
      <AddressFamilyField monitor={monitor} />
      <label>
        Maximum packet loss (%)
        <input
          name="maximum_packet_loss_percent"
          type="number"
          min={0}
          max={100}
          step="0.1"
          defaultValue={optionalConfigNumber(
            monitor,
            'maximum_packet_loss_percent',
          )}
        />
      </label>
      <label>
        Maximum average RTT (ms)
        <input
          name="maximum_average_rtt_ms"
          type="number"
          min={0}
          step="0.1"
          defaultValue={optionalConfigNumber(monitor, 'maximum_average_rtt_ms')}
        />
      </label>
    </div>
  )
}

function HttpFields({ monitor }: { monitor: Monitor | null }) {
  return (
    <div className="form-grid monitor-probe-fields">
      <label>
        Scheme
        <select name="scheme" defaultValue={configString(monitor, 'scheme', 'https')}>
          <option value="https">HTTPS</option>
          <option value="http">HTTP</option>
        </select>
      </label>
      <label>
        Port (optional)
        <input
          name="port"
          type="number"
          min={1}
          max={65535}
          defaultValue={optionalConfigNumber(monitor, 'port')}
        />
      </label>
      <label>
        Path
        <input
          name="path"
          defaultValue={configString(monitor, 'path', '/')}
          required
        />
      </label>
      <label>
        Method
        <select name="method" defaultValue={configString(monitor, 'method', 'GET')}>
          <option value="GET">GET</option>
          <option value="HEAD">HEAD</option>
        </select>
      </label>
      <label>
        Host header (optional)
        <input
          name="host_header"
          defaultValue={configString(monitor, 'host_header', '')}
        />
      </label>
      <AddressFamilyField monitor={monitor} />
      <label>
        Expected status codes
        <input
          name="expected_status_codes"
          defaultValue={configArray(
            monitor,
            'expected_status_codes',
            '200,201,202,204,301,302,303,307,308',
          )}
        />
      </label>
      <label>
        Maximum redirects
        <input
          name="maximum_redirects"
          type="number"
          min={0}
          max={10}
          defaultValue={configNumber(monitor, 'maximum_redirects', 5)}
          required
        />
      </label>
      <label>
        Maximum response bytes
        <input
          name="maximum_response_bytes"
          type="number"
          min={1}
          max={4194304}
          defaultValue={configNumber(monitor, 'maximum_response_bytes', 1048576)}
          required
        />
      </label>
      <label className="checkbox-label">
        <input
          name="follow_redirects"
          type="checkbox"
          defaultChecked={configBoolean(monitor, 'follow_redirects', true)}
        />
        Follow redirects
      </label>
    </div>
  )
}

function TcpFields({ monitor }: { monitor: Monitor | null }) {
  return (
    <div className="form-grid monitor-probe-fields">
      <label>
        Port
        <input
          name="port"
          type="number"
          min={1}
          max={65535}
          defaultValue={optionalConfigNumber(monitor, 'port')}
          required
        />
      </label>
      <AddressFamilyField monitor={monitor} />
    </div>
  )
}

function DnsFields({ monitor }: { monitor: Monitor | null }) {
  return (
    <div className="form-grid monitor-probe-fields">
      <label>
        Resolver mode
        <select
          name="resolver_mode"
          defaultValue={configString(monitor, 'resolver_mode', 'system')}
        >
          <option value="system">System resolver</option>
          <option value="explicit">Explicit resolver</option>
        </select>
      </label>
      <label>
        Resolver address
        <input
          name="resolver_address"
          placeholder="1.1.1.1"
          defaultValue={configString(monitor, 'resolver_address', '')}
        />
      </label>
      <label>
        Resolver port
        <input
          name="resolver_port"
          type="number"
          min={1}
          max={65535}
          defaultValue={configNumber(monitor, 'resolver_port', 53)}
          required
        />
      </label>
      <label>
        Transport
        <select
          name="transport"
          defaultValue={configString(
            monitor,
            'transport',
            'udp_with_tcp_fallback',
          )}
        >
          <option value="udp_with_tcp_fallback">UDP with TCP fallback</option>
          <option value="tcp">TCP</option>
        </select>
      </label>
      <label>
        Query name (optional)
        <input
          name="query_name"
          placeholder="example.com"
          defaultValue={configString(monitor, 'query_name', '')}
        />
      </label>
      <label>
        Query type
        <select
          name="query_type"
          defaultValue={configString(monitor, 'query_type', 'A')}
        >
          {['A', 'AAAA', 'CNAME', 'MX', 'NS', 'TXT', 'PTR'].map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </select>
      </label>
      <label>
        Expected response codes
        <input
          name="expected_response_codes"
          defaultValue={configArray(
            monitor,
            'expected_response_codes',
            'NOERROR',
          )}
        />
      </label>
      <label className="checkbox-label">
        <input
          name="recursion_desired"
          type="checkbox"
          defaultChecked={configBoolean(monitor, 'recursion_desired', true)}
        />
        Recursion desired
      </label>
    </div>
  )
}

function TlsFields({ monitor }: { monitor: Monitor | null }) {
  return (
    <div className="form-grid monitor-probe-fields">
      <label>
        Port
        <input
          name="port"
          type="number"
          min={1}
          max={65535}
          defaultValue={configNumber(monitor, 'port', 443)}
          required
        />
      </label>
      <label>
        Server name (optional)
        <input
          name="server_name"
          placeholder="example.com"
          defaultValue={configString(monitor, 'server_name', '')}
        />
      </label>
      <AddressFamilyField monitor={monitor} />
      <label>
        Minimum TLS version
        <select
          name="minimum_tls_version"
          defaultValue={configString(monitor, 'minimum_tls_version', '1.2')}
        >
          <option value="1.2">TLS 1.2</option>
          <option value="1.3">TLS 1.3</option>
        </select>
      </label>
      <label>
        Expiry warning (days)
        <input
          name="expiry_warning_days"
          type="number"
          min={0}
          max={3650}
          defaultValue={configNumber(monitor, 'expiry_warning_days', 30)}
          required
        />
      </label>
    </div>
  )
}

export function MonitorFields({
  targets,
  monitor = null,
  includeTarget = true,
  nameField = 'name',
  nameLabel = 'Name',
  defaultName,
}: {
  targets: Target[]
  monitor?: Monitor | null
  includeTarget?: boolean
  nameField?: string
  nameLabel?: string
  defaultName?: string
}) {
  const [probeType, setProbeType] = useState<ProbeType>(
    monitor?.probe_type ?? 'icmp',
  )

  const configurationMonitor =
    monitor?.probe_type === probeType ? monitor : null

  return (
    <>
      <div className="form-grid">
        <label>
          {nameLabel}
          <input
            name={nameField}
            required
            maxLength={200}
            defaultValue={defaultName ?? monitor?.name ?? ''}
          />
        </label>
        {includeTarget ? (
          <label>
            Target
            <select name="target_id" defaultValue={monitor?.target_id ?? ''} required>
              <option value="" disabled>
                Select target
              </option>
              {targets.map((target) => (
                <option key={target.id} value={target.id}>
                  {target.name} — {target.address}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <label>
          Probe type
          <select
            name="probe_type"
            value={probeType}
            onChange={(event) => setProbeType(event.target.value as ProbeType)}
          >
            {(Object.keys(probeLabels) as ProbeType[]).map((type) => (
              <option key={type} value={type}>
                {probeLabels[type]}
              </option>
            ))}
          </select>
        </label>
        <label>
          Interval (seconds)
          <input
            name="interval_seconds"
            type="number"
            min={1}
            defaultValue={monitor?.interval_seconds ?? 60}
            required
          />
        </label>
        <label>
          Timeout (seconds)
          <input
            name="timeout_seconds"
            type="number"
            min={1}
            defaultValue={monitor?.timeout_seconds ?? 10}
            required
          />
        </label>
      </div>
      <label>
        Description
        <textarea
          name="description"
          rows={2}
          defaultValue={monitor?.description ?? ''}
        />
      </label>

      <div className="probe-configuration" key={probeType}>
        <div>
          <span className="eyebrow">Probe configuration</span>
          <h3>{probeLabels[probeType]}</h3>
        </div>
        {probeType === 'icmp' ? (
          <IcmpFields monitor={configurationMonitor} />
        ) : null}
        {probeType === 'http' ? (
          <HttpFields monitor={configurationMonitor} />
        ) : null}
        {probeType === 'tcp' ? (
          <TcpFields monitor={configurationMonitor} />
        ) : null}
        {probeType === 'dns' ? (
          <DnsFields monitor={configurationMonitor} />
        ) : null}
        {probeType === 'tls' ? (
          <TlsFields monitor={configurationMonitor} />
        ) : null}
      </div>
    </>
  )
}
