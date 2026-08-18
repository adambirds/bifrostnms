# Bulk monitor creation

BifrostNMS keeps monitor identity explicit: one `Monitor` belongs to one `Target`.
That makes revision history, observations, health state and future declarative
configuration predictable even when target-group membership changes.

The dashboard and API provide bulk operations so this model does not require
repeating the same configuration by hand.

## Dashboard workflow

Open **Monitors** and use **Bulk create or duplicate monitors**.

A bulk operation can target either:

- every target directly contained in one target group; or
- a manually selected set of targets.

Target-group expansion happens when the operation is submitted. Adding a target
to the group later does not silently create a monitor, and removing a target does
not delete its monitor or history.

### Create a shared monitor definition

Choose **Create a new shared definition**, then configure the probe exactly as a
normal monitor. This is useful for common checks such as ICMP latency/loss or a
standard TCP port.

The same validated probe configuration is used to create an explicit monitor for
each selected target.

### Duplicate an existing monitor

Choose **Duplicate an existing monitor** and select a source monitor. BifrostNMS
copies its probe type, schedule, timeout, description and normalized probe
configuration to each selected target.

Each configured monitor row also has a **Duplicate** action. It opens the bulk
form in duplicate mode with that monitor already selected as the source.

The new monitors get their own UUIDs and revision/history lifecycle; they are not
linked aliases of the source monitor.

## Name templates

Bulk-created monitors need realm-unique names. The name template supports:

- `{target}` - target display name;
- `{address}` - target address;
- `{probe}` - upper-case probe type; and
- `{source}` - source monitor name when duplicating.

For example:

```text
{target} - {probe}
```

can create `Router - ICMP` and `Website - ICMP` in one operation.

## Agent assignments

The bulk form can assign every created monitor to selected individual agents and
agent groups during the same operation. This avoids creating a set of monitors
and then repeating the same vantage-point assignments manually.

Agent-group assignment keeps its normal semantics: the monitor runs from the
eligible direct members of that agent group. Target groups and agent groups are
independent concepts.

## Apply only to missing targets

**Skip targets that already have an equivalent monitor** is enabled by default.
Before creating a monitor, the control plane normalizes the probe configuration
and checks the target for an active monitor with the same probe type, interval,
timeout and normalized configuration.

This makes the bulk form suitable for an explicit "apply to missing targets"
workflow after a target group grows. Existing equivalent monitors and their
history remain untouched.

A skipped target is reported separately from successfully created monitors.
Disabled targets are also skipped rather than silently enabled.

## API

The dashboard uses:

```http
POST /api/v1/monitoring/monitors/bulk
```

The request can provide `target_ids`, a `target_group_id`, or both. It can either
provide a new typed monitor definition or a `source_monitor_id` to duplicate.
Optional `agent_ids` and `agent_group_ids` are applied to every new monitor.

A representative request is:

```json
{
  "target_group_id": "00000000-0000-0000-0000-000000000000",
  "target_ids": [],
  "source_monitor_id": null,
  "name_template": "{target} - {probe}",
  "probe_type": "icmp",
  "interval_seconds": 30,
  "timeout_seconds": 5,
  "configuration": {},
  "agent_ids": [],
  "agent_group_ids": ["11111111-1111-1111-1111-111111111111"],
  "skip_existing": true
}
```

The response contains separate `created` and `skipped` collections so callers
can report partial success without treating expected existing coverage as a
failure.

## Architecture boundary

Bulk creation is deliberately an explicit command, not a persistent
monitor-to-target-group relationship. This preserves the architecture in
`docs/architecture/data-model.md`: later group-membership edits cannot silently
change scheduling, create new monitor identities or destroy historical context.
