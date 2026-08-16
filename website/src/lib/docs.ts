export type DocSection = {
  heading: string
  paragraphs?: string[]
  bullets?: string[]
  code?: string
  note?: string
}

export type UserGuide = {
  slug: string
  title: string
  summary: string
  sections: DocSection[]
}

export const userGuides: UserGuide[] = [
  {
    slug: 'getting-started',
    title: 'Getting started',
    summary:
      'Bootstrap a local BifrostNMS installation and reach the dashboard for the first time.',
    sections: [
      {
        heading: 'Start from the Dev Container',
        paragraphs: [
          'The supported development workflow uses the repository Dev Container so PostgreSQL/TimescaleDB, Redis and the application tooling use the versions expected by the project.',
          'On a fresh database, run the bootstrap command before starting the applications.',
        ],
        code: './tools/db-bootstrap',
      },
      {
        heading: 'Create the installation administrator',
        paragraphs: [
          'The installation superuser is global to the control plane. The command also makes sure a first realm exists so a fresh self-hosted installation is immediately usable.',
        ],
        code: './tools/create-superuser --realm-name "Local"',
      },
      {
        heading: 'Start the web applications',
        paragraphs: [
          'You can use the VS Code task “start: all web”, or start each application in its own terminal.',
        ],
        code: 'PYTHONPATH=backend uvicorn bifrostnms.main:app --reload --host 0.0.0.0 --port 8000\npnpm --dir auth-frontend dev\npnpm --dir frontend dev',
        bullets: [
          'Dashboard: http://localhost:3000',
          'Authentication/account application: http://localhost:3001',
          'FastAPI control plane: http://localhost:8000',
        ],
      },
      {
        heading: 'Sign in',
        paragraphs: [
          'Sign in through the authentication application. BifrostNMS stores the opaque browser session in Redis and shares it between the auth application and dashboard.',
          'The dashboard always operates inside one active realm. A superuser has installation-wide access, but still receives an active realm in the session so monitoring queries have an explicit tenant boundary.',
        ],
      },
    ],
  },
  {
    slug: 'realms',
    title: 'Realms and access',
    summary:
      'Understand the tenant boundary used by self-hosted installations and BifrostNMS Cloud.',
    sections: [
      {
        heading: 'What a realm is',
        paragraphs: [
          'A realm is the persistent tenant and authorization boundary for monitoring configuration and observations. Most self-hosted installations will use one realm, but the data model supports several without changing architecture.',
        ],
        bullets: [
          'Users are installation-wide identities.',
          'Normal realm access is granted through realm memberships.',
          'Agents, groups, targets, monitors, assignments and observations all belong to a realm.',
          'Installation superusers may access every active realm without an explicit membership.',
        ],
      },
      {
        heading: 'Active realm',
        paragraphs: [
          'Your browser session contains an active realm ID. Every monitoring API request is authorized against that realm before data is read or changed. The dashboard shows the active realm in the sidebar so the context is visible while you work.',
        ],
      },
    ],
  },
  {
    slug: 'agents',
    title: 'Agents and enrolment',
    summary:
      'Create an agent, enrol a Go process and understand offline operation.',
    sections: [
      {
        heading: 'Create an agent',
        paragraphs: [
          'Open Agents in the dashboard and create a record for each monitoring vantage point. An agent record represents a specific monitoring process/location; it is not enrolled until the process exchanges a one-time token for its own credential.',
        ],
      },
      {
        heading: 'Issue the one-time token',
        paragraphs: [
          'Use “Issue enrolment token” on the agent. The raw token is intentionally displayed only in the creation response and cannot be recovered later. Issuing a replacement invalidates the previous unused token.',
        ],
        note: 'Treat the enrolment token as a secret. The dashboard’s suggested shell workflow reads it without echoing it into shell history.',
      },
      {
        heading: 'Enrol the process',
        code: 'read -s BIFROSTNMS_AGENT_ENROLMENT_TOKEN\nexport BIFROSTNMS_AGENT_ENROLMENT_TOKEN\ncd agent\ngo run ./cmd/bifrost-agent enrol --control-plane http://localhost:8000',
        paragraphs: [
          'Successful enrolment stores the stable agent identity, control-plane URL and issued credential in the agent SQLite database. The server stores only the credential digest.',
        ],
      },
      {
        heading: 'Run the agent',
        code: 'cd agent\ngo run ./cmd/bifrost-agent',
        paragraphs: [
          'The agent sends heartbeats, pulls immutable desired-configuration snapshots, schedules probes locally, queues observations in SQLite and uploads them in batches.',
          'If the control plane or network is unavailable, the agent keeps the last valid configuration and continues monitoring. Pending observations synchronize after connectivity returns.',
        ],
      },
    ],
  },
  {
    slug: 'targets-groups',
    title: 'Targets and groups',
    summary:
      'Model destinations and organize agents or targets without hiding monitoring behavior.',
    sections: [
      {
        heading: 'Targets',
        paragraphs: [
          'A target is a reusable hostname or IP address. It deliberately does not contain a port, URL path, DNS record type or probe schedule; those belong to monitors so one target can be observed in several different ways.',
        ],
      },
      {
        heading: 'Agent groups',
        paragraphs: [
          'Agent groups are hierarchical and can contain the same agent in multiple groups. Assigning a monitor to an agent group is an explicit execution relationship: each enabled member becomes an effective vantage point for that monitor.',
        ],
      },
      {
        heading: 'Target groups',
        paragraphs: [
          'Target groups are for hierarchy, navigation and explicit bulk workflows. Merely placing a target in a group does not silently create monitors or assignments.',
        ],
      },
    ],
  },
  {
    slug: 'monitors',
    title: 'Monitors and assignments',
    summary:
      'Define a probe, schedule it and choose the vantage points that execute it.',
    sections: [
      {
        heading: 'Create a monitor',
        paragraphs: [
          'A monitor combines one target with a probe type, interval, timeout and validated probe-specific configuration. The dashboard uses the same typed management contracts that future automation will use.',
        ],
        bullets: [
          'Interval controls how often the autonomous agent schedules the probe.',
          'Timeout must be shorter than the interval.',
          'Probe configuration is validated by FastAPI before it becomes desired agent configuration.',
          'Changing execution behavior increments the monitor revision.',
        ],
      },
      {
        heading: 'Assign vantage points',
        paragraphs: [
          'A monitor does nothing until it has at least one effective assignment. Assign it directly to an agent, to an agent group, or both. Effective agents are deduplicated, so overlapping direct/group assignments do not run duplicate copies of the monitor.',
        ],
      },
      {
        heading: 'Configuration acknowledgement',
        paragraphs: [
          'After a change, the control plane bumps desired configuration for affected agents. Until an agent downloads and acknowledges that revision, the dashboard reports Pending configuration rather than treating missing results as a monitoring failure.',
        ],
      },
    ],
  },
  {
    slug: 'probes',
    title: 'Native probes',
    summary:
      'Configure the V1 native probe families without external command-line tools.',
    sections: [
      {
        heading: 'ICMP',
        bullets: [
          'Runs natively in Go rather than invoking fping.',
          'Stores individual successful RTT samples as well as sent/received counts and packet loss.',
          'Calculates min, average, median, max, P95 and jitter for visualization and summaries.',
          'Supports explicit IPv4/IPv6 behavior and optional loss/latency assessment thresholds.',
        ],
      },
      {
        heading: 'HTTP / HTTPS',
        bullets: [
          'Supports GET and HEAD, redirect limits and bounded response reads.',
          'Records DNS, connection, TLS, time-to-first-byte and total timing where available.',
          'Can assert expected status, headers and body content.',
          'HTTPS keeps normal certificate verification enabled.',
        ],
      },
      {
        heading: 'TCP',
        bullets: [
          'Measures TCP connection duration to a configured port.',
          'Keeps target/network failures distinct from local execution failures.',
          'Supports automatic, IPv4-only and IPv6-only address selection.',
        ],
      },
      {
        heading: 'DNS',
        bullets: [
          'Supports the system resolver or an explicit resolver.',
          'Supports A, AAAA, CNAME, MX, NS, TXT and PTR queries.',
          'Uses UDP with TCP fallback for truncated replies, or explicit TCP.',
          'Stores normalized answers, response code, timing and assertion results.',
        ],
      },
      {
        heading: 'TLS certificate',
        bullets: [
          'Performs a real TLS handshake with hostname and chain verification.',
          'Stores protocol/cipher, subject, issuer, validity, fingerprint and remaining validity.',
          'Distinguishes expiry, hostname mismatch and untrusted certificate failures.',
          'Does not offer an insecure “skip verification” monitor option.',
        ],
      },
    ],
  },
  {
    slug: 'results',
    title: 'Reading monitoring results',
    summary:
      'Understand current state, gaps, distributed disagreement and SmokePing-style history.',
    sections: [
      {
        heading: 'Current state is not just red or green',
        paragraphs: [
          'BifrostNMS separates agent connectivity, probe execution, target assessment and data coverage so the dashboard does not blame a target for a broken monitoring path.',
        ],
        bullets: [
          'Healthy: a current observation completed and met the configured assessment.',
          'Unhealthy: a current observation completed normally but the target failed its assessment.',
          'Probe error: execution failed before a normal target assessment could be produced.',
          'Missing data: the expected observation is overdue even though monitoring should be active.',
          'Agent stale/offline: the monitoring vantage point itself is not currently trustworthy.',
          'Pending configuration: the affected agent has not acknowledged the desired revision yet.',
        ],
      },
      {
        heading: 'Distributed monitor headline',
        paragraphs: [
          'A monitor is only globally Healthy or Unhealthy when all trustworthy effective agents agree. Mixed results become Degraded. If no trustworthy current result exists, the headline is Unknown rather than assuming failure or success.',
        ],
      },
      {
        heading: 'SmokePing-style ICMP history',
        paragraphs: [
          'The ICMP graph plots the individual RTT samples retained for each observation instead of reducing a run to one average. Median lines are separated by agent and packet loss is shown independently.',
          'A missing expected observation breaks the line. BifrostNMS never draws a gap as zero latency or silently interpolates successful continuity.',
        ],
      },
      {
        heading: 'Probe-specific history',
        paragraphs: [
          'The monitor detail view keeps the native result shape visible: HTTP phase timings and assertions, TCP connect timing, DNS response/answers, and TLS handshake/certificate state are shown from their typed TimescaleDB result tables.',
        ],
      },
    ],
  },
  {
    slug: 'local-testing',
    title: 'Local Stage 9 test walkthrough',
    summary:
      'Exercise the complete V1 dashboard workflow on a development installation.',
    sections: [
      {
        heading: '1. Bootstrap and sign in',
        code: './tools/db-bootstrap\n./tools/create-superuser --realm-name "Local"',
        bullets: [
          'Start API, auth frontend and dashboard using the VS Code “start: all web” task.',
          'Sign in at http://localhost:3001 and open http://localhost:3000.',
          'Confirm the sidebar shows the Local realm and the overview renders explicit empty states.',
        ],
      },
      {
        heading: '2. Create two vantage points',
        bullets: [
          'Create agents named, for example, London and Manchester.',
          'Issue an enrolment token for London and enrol one local agent process.',
          'For a true cross-agent test, run a second agent with a different BIFROSTNMS_AGENT_DATABASE_PATH and enrol it against Manchester.',
          'Confirm the Agents page begins receiving heartbeat/platform/capability information.',
        ],
      },
      {
        heading: '3. Build the configuration',
        bullets: [
          'Create one or more targets using hostnames/IPs you are allowed to monitor.',
          'Create agent and target groups and test add/remove membership.',
          'Create an ICMP monitor and at least one HTTP, TCP, DNS or TLS monitor.',
          'Assign monitors directly and through a group; confirm duplicate effective assignments do not result in duplicate execution.',
          'Edit a monitor and confirm its revision changes only when agent-facing behavior changes.',
        ],
      },
      {
        heading: '4. Observe configuration activation',
        paragraphs: [
          'Immediately after an assignment or monitor behavior change, expect Pending configuration. After the running agent polls and acknowledges the new snapshot, the state should progress to No data yet and then a measured state.',
        ],
      },
      {
        heading: '5. Check historical views',
        bullets: [
          'Open a monitor using View and switch between 1h, 6h, 24h, 7d and 30d ranges.',
          'For ICMP, confirm individual RTT samples, packet loss and separate per-agent medians are visible.',
          'Stop one agent long enough to become stale/offline and confirm the target is not mislabeled unhealthy merely because that vantage point disappeared.',
          'Stop the control plane while an agent keeps running, then restart it and confirm queued observations synchronize without duplicated observation IDs.',
          'Create a deliberate observation gap and confirm the ICMP median line breaks instead of dropping to zero.',
        ],
      },
      {
        heading: '6. Run repository validation',
        code: './tools/test-all\n./tools/lint',
        paragraphs: [
          'A Stage 9 build is not considered validated until the backend tests, dashboard behavior tests, type checks, linters and production builds all pass.',
        ],
      },
    ],
  },
]

export function getUserGuide(slug: string): UserGuide | undefined {
  return userGuides.find((guide) => guide.slug === slug)
}
