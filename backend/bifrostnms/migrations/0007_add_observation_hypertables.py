from tortoise import migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [("models", "0006_add_monitoring_domain")]

    initial = False

    operations = [
        ops.RunSQL(
            """
            CREATE TABLE observations (
                scheduled_at TIMESTAMPTZ NOT NULL,
                observation_id UUID NOT NULL,
                realm_id UUID NOT NULL,
                agent_id UUID NOT NULL,
                monitor_id UUID NOT NULL,
                probe_type VARCHAR(16) NOT NULL,
                monitor_revision BIGINT NOT NULL,
                agent_config_revision BIGINT NOT NULL,
                started_at TIMESTAMPTZ NOT NULL,
                finished_at TIMESTAMPTZ NOT NULL,
                received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                execution_status VARCHAR(16) NOT NULL,
                assessment VARCHAR(16) NOT NULL,
                error_category VARCHAR(32),
                error_code VARCHAR(120),
                error_message VARCHAR(500),
                agent_clock_offset_ms INTEGER,
                CONSTRAINT observations_identity_uniq
                    UNIQUE (scheduled_at, observation_id),
                CONSTRAINT observations_probe_type_valid
                    CHECK (probe_type IN ('icmp', 'http', 'tcp', 'dns', 'tls')),
                CONSTRAINT observations_execution_status_valid
                    CHECK (execution_status IN ('completed', 'failed')),
                CONSTRAINT observations_assessment_valid
                    CHECK (assessment IN ('healthy', 'unhealthy', 'unknown')),
                CONSTRAINT observations_error_category_valid CHECK (
                    error_category IS NULL OR error_category IN (
                        'timeout', 'resolution', 'connection', 'tls', 'protocol',
                        'assertion', 'permission', 'invalid_configuration',
                        'resource_limit', 'internal'
                    )
                ),
                CONSTRAINT observations_revisions_positive CHECK (
                    monitor_revision > 0 AND agent_config_revision > 0
                ),
                CONSTRAINT observations_timestamps_ordered CHECK (
                    started_at >= scheduled_at AND finished_at >= started_at
                )
            );

            SELECT create_hypertable(
                'observations',
                by_range('scheduled_at', INTERVAL '7 days')
            );

            CREATE INDEX observations_realm_monitor_agent_scheduled_idx
                ON observations (realm_id, monitor_id, agent_id, scheduled_at DESC);
            CREATE INDEX observations_realm_agent_scheduled_idx
                ON observations (realm_id, agent_id, scheduled_at DESC);
            CREATE INDEX observations_realm_assessment_scheduled_idx
                ON observations (realm_id, assessment, scheduled_at DESC);
            CREATE INDEX observations_realm_received_idx
                ON observations (realm_id, received_at DESC);

            CREATE TABLE icmp_results (
                scheduled_at TIMESTAMPTZ NOT NULL,
                observation_id UUID NOT NULL,
                realm_id UUID NOT NULL,
                agent_id UUID NOT NULL,
                monitor_id UUID NOT NULL,
                packets_sent INTEGER NOT NULL,
                packets_received INTEGER NOT NULL,
                packet_loss_percent DOUBLE PRECISION NOT NULL,
                min_rtt_ms DOUBLE PRECISION,
                avg_rtt_ms DOUBLE PRECISION,
                median_rtt_ms DOUBLE PRECISION,
                max_rtt_ms DOUBLE PRECISION,
                p95_rtt_ms DOUBLE PRECISION,
                jitter_ms DOUBLE PRECISION,
                rtt_samples_ms DOUBLE PRECISION[] NOT NULL,
                CONSTRAINT icmp_results_identity_uniq
                    UNIQUE (scheduled_at, observation_id),
                CONSTRAINT icmp_results_packet_counts_valid CHECK (
                    packets_sent BETWEEN 1 AND 20
                    AND packets_received BETWEEN 0 AND packets_sent
                    AND cardinality(rtt_samples_ms) = packets_received
                ),
                CONSTRAINT icmp_results_packet_loss_valid
                    CHECK (packet_loss_percent BETWEEN 0 AND 100),
                CONSTRAINT icmp_results_rtt_values_valid CHECK (
                    min_rtt_ms IS NULL OR min_rtt_ms >= 0
                )
            );

            CREATE TABLE http_results (
                scheduled_at TIMESTAMPTZ NOT NULL,
                observation_id UUID NOT NULL,
                realm_id UUID NOT NULL,
                agent_id UUID NOT NULL,
                monitor_id UUID NOT NULL,
                method VARCHAR(8) NOT NULL,
                scheme VARCHAR(8) NOT NULL,
                status_code INTEGER,
                redirect_count INTEGER NOT NULL,
                response_size_bytes BIGINT,
                dns_ms DOUBLE PRECISION,
                connect_ms DOUBLE PRECISION,
                tls_ms DOUBLE PRECISION,
                ttfb_ms DOUBLE PRECISION,
                total_ms DOUBLE PRECISION,
                assertions_total INTEGER NOT NULL,
                assertions_failed INTEGER NOT NULL,
                final_url_redacted VARCHAR(2048),
                CONSTRAINT http_results_identity_uniq
                    UNIQUE (scheduled_at, observation_id),
                CONSTRAINT http_results_method_valid CHECK (method IN ('GET', 'HEAD')),
                CONSTRAINT http_results_scheme_valid CHECK (scheme IN ('http', 'https')),
                CONSTRAINT http_results_status_valid
                    CHECK (status_code IS NULL OR status_code BETWEEN 100 AND 599),
                CONSTRAINT http_results_counts_valid CHECK (
                    redirect_count >= 0
                    AND assertions_total >= 0
                    AND assertions_failed BETWEEN 0 AND assertions_total
                    AND (response_size_bytes IS NULL OR response_size_bytes >= 0)
                )
            );

            CREATE TABLE tcp_results (
                scheduled_at TIMESTAMPTZ NOT NULL,
                observation_id UUID NOT NULL,
                realm_id UUID NOT NULL,
                agent_id UUID NOT NULL,
                monitor_id UUID NOT NULL,
                port INTEGER NOT NULL,
                address_used INET NOT NULL,
                connect_ms DOUBLE PRECISION,
                CONSTRAINT tcp_results_identity_uniq
                    UNIQUE (scheduled_at, observation_id),
                CONSTRAINT tcp_results_port_valid CHECK (port BETWEEN 1 AND 65535),
                CONSTRAINT tcp_results_connect_valid
                    CHECK (connect_ms IS NULL OR connect_ms >= 0)
            );

            CREATE TABLE dns_results (
                scheduled_at TIMESTAMPTZ NOT NULL,
                observation_id UUID NOT NULL,
                realm_id UUID NOT NULL,
                agent_id UUID NOT NULL,
                monitor_id UUID NOT NULL,
                resolver_address INET NOT NULL,
                query_name VARCHAR(253) NOT NULL,
                query_type VARCHAR(16) NOT NULL,
                response_code VARCHAR(32),
                response_ms DOUBLE PRECISION,
                answer_count INTEGER NOT NULL,
                answers JSONB NOT NULL,
                truncated BOOLEAN NOT NULL,
                authoritative BOOLEAN NOT NULL,
                assertions_total INTEGER NOT NULL,
                assertions_failed INTEGER NOT NULL,
                CONSTRAINT dns_results_identity_uniq
                    UNIQUE (scheduled_at, observation_id),
                CONSTRAINT dns_results_query_type_valid CHECK (
                    query_type IN ('A', 'AAAA', 'CNAME', 'MX', 'NS', 'PTR', 'SOA', 'TXT')
                ),
                CONSTRAINT dns_results_values_valid CHECK (
                    (response_ms IS NULL OR response_ms >= 0)
                    AND answer_count >= 0
                    AND jsonb_typeof(answers) = 'array'
                    AND assertions_total >= 0
                    AND assertions_failed BETWEEN 0 AND assertions_total
                )
            );

            CREATE TABLE tls_results (
                scheduled_at TIMESTAMPTZ NOT NULL,
                observation_id UUID NOT NULL,
                realm_id UUID NOT NULL,
                agent_id UUID NOT NULL,
                monitor_id UUID NOT NULL,
                port INTEGER NOT NULL,
                server_name VARCHAR(253) NOT NULL,
                protocol_version VARCHAR(32),
                cipher_suite VARCHAR(160),
                handshake_ms DOUBLE PRECISION,
                certificate_present BOOLEAN NOT NULL,
                hostname_valid BOOLEAN,
                chain_valid BOOLEAN,
                not_before TIMESTAMPTZ,
                not_after TIMESTAMPTZ,
                days_remaining DOUBLE PRECISION,
                subject_name VARCHAR(500),
                issuer_name VARCHAR(500),
                serial_number VARCHAR(160),
                fingerprint_sha256 VARCHAR(64),
                CONSTRAINT tls_results_identity_uniq
                    UNIQUE (scheduled_at, observation_id),
                CONSTRAINT tls_results_port_valid CHECK (port BETWEEN 1 AND 65535),
                CONSTRAINT tls_results_handshake_valid
                    CHECK (handshake_ms IS NULL OR handshake_ms >= 0),
                CONSTRAINT tls_results_certificate_dates_valid CHECK (
                    not_before IS NULL OR not_after IS NULL OR not_after >= not_before
                )
            );

            SELECT create_hypertable(
                'icmp_results', by_range('scheduled_at', INTERVAL '7 days')
            );
            SELECT create_hypertable(
                'http_results', by_range('scheduled_at', INTERVAL '7 days')
            );
            SELECT create_hypertable(
                'tcp_results', by_range('scheduled_at', INTERVAL '7 days')
            );
            SELECT create_hypertable(
                'dns_results', by_range('scheduled_at', INTERVAL '7 days')
            );
            SELECT create_hypertable(
                'tls_results', by_range('scheduled_at', INTERVAL '7 days')
            );

            CREATE INDEX icmp_results_realm_monitor_agent_scheduled_idx
                ON icmp_results (realm_id, monitor_id, agent_id, scheduled_at DESC);
            CREATE INDEX http_results_realm_monitor_agent_scheduled_idx
                ON http_results (realm_id, monitor_id, agent_id, scheduled_at DESC);
            CREATE INDEX tcp_results_realm_monitor_agent_scheduled_idx
                ON tcp_results (realm_id, monitor_id, agent_id, scheduled_at DESC);
            CREATE INDEX dns_results_realm_monitor_agent_scheduled_idx
                ON dns_results (realm_id, monitor_id, agent_id, scheduled_at DESC);
            CREATE INDEX tls_results_realm_monitor_agent_scheduled_idx
                ON tls_results (realm_id, monitor_id, agent_id, scheduled_at DESC);
            """,
            reverse_sql="""
            DROP TABLE tls_results;
            DROP TABLE dns_results;
            DROP TABLE tcp_results;
            DROP TABLE http_results;
            DROP TABLE icmp_results;
            DROP TABLE observations;
            """,
        )
    ]
