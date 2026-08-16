package icmp

import (
	"encoding/json"
	"testing"
	"time"
)

func TestConfigurationMaterializesDefaultsAndRejectsUnknownFields(t *testing.T) {
	configuration, err := DecodeConfiguration(json.RawMessage(`{"schema_version":1}`))
	if err != nil {
		t.Fatalf("decode default configuration: %v", err)
	}
	if configuration.PacketCount != 20 || configuration.PacketIntervalMS != 50 ||
		configuration.PayloadSizeBytes != 56 || configuration.AddressFamily != AddressFamilyAuto {
		t.Fatalf("default configuration = %#v", configuration)
	}
	if _, err := DecodeConfiguration(json.RawMessage(`{"schema_version":1,"command":"ping"}`)); err == nil {
		t.Fatal("unknown ICMP configuration field was accepted")
	}
}

func TestConfigurationEnsuresPacketSequenceFitsMonitorTimeout(t *testing.T) {
	configuration := DefaultConfiguration()
	packetTimeout, err := configuration.Timeout(2 * time.Second)
	if err != nil || packetTimeout != 1050*time.Millisecond {
		t.Fatalf("derived packet timeout = %v, error = %v", packetTimeout, err)
	}
	configuration.PerPacketTimeoutMS = 100
	if _, err := configuration.Timeout(1100 * time.Millisecond); err != nil {
		t.Fatalf("valid explicit timeout: %v", err)
	}
	configuration.PerPacketTimeoutMS = 151
	if _, err := configuration.Timeout(1100 * time.Millisecond); err == nil {
		t.Fatal("packet sequence exceeding monitor timeout was accepted")
	}
}

func TestConfigurationRejectsUnsafeBounds(t *testing.T) {
	for name, content := range map[string]string{
		"packet count":    `{"schema_version":1,"packet_count":101}`,
		"packet interval": `{"schema_version":1,"packet_interval_ms":9}`,
		"payload size":    `{"schema_version":1,"payload_size_bytes":1401}`,
		"address family":  `{"schema_version":1,"address_family":"either"}`,
		"packet loss":     `{"schema_version":1,"maximum_packet_loss_percent":101}`,
	} {
		t.Run(name, func(t *testing.T) {
			if _, err := DecodeConfiguration(json.RawMessage(content)); err == nil {
				t.Fatal("unsafe configuration was accepted")
			}
		})
	}
}
