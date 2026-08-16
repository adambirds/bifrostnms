import type { ProbeType } from '@/lib/monitoring'

function optionalNumber(formData: FormData, name: string): number | null {
  const raw = String(formData.get(name) ?? '').trim()
  return raw ? Number(raw) : null
}

export function requiredNumber(formData: FormData, name: string): number {
  return Number(String(formData.get(name) ?? '').trim())
}

function addressFamily(formData: FormData): 'auto' | 'ipv4' | 'ipv6' {
  const value = String(formData.get('address_family') ?? 'auto')
  return value === 'ipv4' || value === 'ipv6' ? value : 'auto'
}

export function buildMonitorConfiguration(
  probeType: ProbeType,
  formData: FormData,
): Record<string, unknown> {
  const schemaVersion = 1

  switch (probeType) {
    case 'icmp':
      return {
        schema_version: schemaVersion,
        packet_count: requiredNumber(formData, 'packet_count'),
        packet_interval_ms: requiredNumber(formData, 'packet_interval_ms'),
        payload_size_bytes: requiredNumber(formData, 'payload_size_bytes'),
        address_family: addressFamily(formData),
        maximum_packet_loss_percent: optionalNumber(
          formData,
          'maximum_packet_loss_percent',
        ),
        maximum_average_rtt_ms: optionalNumber(
          formData,
          'maximum_average_rtt_ms',
        ),
      }
    case 'http': {
      const port = optionalNumber(formData, 'port')
      const expectedStatusCodes = String(
        formData.get('expected_status_codes') ??
          '200,201,202,204,301,302,303,307,308',
      )
        .split(',')
        .map((value) => Number(value.trim()))
        .filter((value) => Number.isInteger(value))

      return {
        schema_version: schemaVersion,
        scheme: String(formData.get('scheme') ?? 'https'),
        port,
        path: String(formData.get('path') ?? '/').trim() || '/',
        method: String(formData.get('method') ?? 'GET'),
        follow_redirects: formData.get('follow_redirects') === 'on',
        maximum_redirects: requiredNumber(formData, 'maximum_redirects'),
        host_header: String(formData.get('host_header') ?? '').trim() || null,
        request_headers: {},
        expected_status_codes: expectedStatusCodes,
        expected_header_values: [],
        expected_body_contains: [],
        maximum_response_bytes: requiredNumber(
          formData,
          'maximum_response_bytes',
        ),
        address_family: addressFamily(formData),
      }
    }
    case 'tcp':
      return {
        schema_version: schemaVersion,
        port: requiredNumber(formData, 'port'),
        address_family: addressFamily(formData),
      }
    case 'dns': {
      const resolverMode = String(formData.get('resolver_mode') ?? 'system')
      return {
        schema_version: schemaVersion,
        resolver_mode: resolverMode,
        resolver_address:
          resolverMode === 'explicit'
            ? String(formData.get('resolver_address') ?? '').trim()
            : null,
        resolver_port: requiredNumber(formData, 'resolver_port'),
        transport: String(formData.get('transport') ?? 'udp_with_tcp_fallback'),
        query_name: String(formData.get('query_name') ?? '').trim() || null,
        query_type: String(formData.get('query_type') ?? 'A'),
        recursion_desired: formData.get('recursion_desired') === 'on',
        expected_response_codes: String(
          formData.get('expected_response_codes') ?? 'NOERROR',
        )
          .split(',')
          .map((value) => value.trim().toUpperCase())
          .filter(Boolean),
        expected_answers: [],
      }
    }
    case 'tls':
      return {
        schema_version: schemaVersion,
        port: requiredNumber(formData, 'port'),
        server_name: String(formData.get('server_name') ?? '').trim() || null,
        address_family: addressFamily(formData),
        minimum_tls_version: String(
          formData.get('minimum_tls_version') ?? '1.2',
        ),
        expiry_warning_days: requiredNumber(formData, 'expiry_warning_days'),
      }
  }
}
