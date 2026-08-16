from tortoise import migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [("models", "0011_add_observation_content_hash")]

    initial = False

    operations = [
        ops.RunSQL(
            """
            ALTER TABLE icmp_results
                DROP CONSTRAINT icmp_results_packet_counts_valid;
            ALTER TABLE icmp_results
                ADD CONSTRAINT icmp_results_packet_counts_valid CHECK (
                    packets_sent BETWEEN 1 AND 100
                    AND packets_received BETWEEN 0 AND packets_sent
                    AND cardinality(rtt_samples_ms) = packets_received
                );
            """,
            reverse_sql="""
            ALTER TABLE icmp_results
                DROP CONSTRAINT icmp_results_packet_counts_valid;
            ALTER TABLE icmp_results
                ADD CONSTRAINT icmp_results_packet_counts_valid CHECK (
                    packets_sent BETWEEN 1 AND 20
                    AND packets_received BETWEEN 0 AND packets_sent
                    AND cardinality(rtt_samples_ms) = packets_received
                );
            """,
        )
    ]
