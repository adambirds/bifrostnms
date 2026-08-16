package tls

import (
	"encoding/json"
	"errors"
	"net"
	"strings"

	"github.com/adambirds/bifrostnms/agent/probe"
)

const (
	ConfigurationSchemaVersion uint32 = 1
	ResultSchemaVersion        uint32 = 1
)

type AddressFamily string

type MinimumTLSVersion string

const (
	AddressFamilyAuto AddressFamily = "auto"
	AddressFamilyIPv4 AddressFamily = "ipv4"
	AddressFamilyIPv6 AddressFamily = "ipv6"

	MinimumTLS12 MinimumTLSVersion = "1.2"
	MinimumTLS13 MinimumTLSVersion = "1.3"
)

type Configuration struct {
	SchemaVersion     uint32            `json:"schema_version"`
	Port              int               `json:"port"`
	ServerName        *string           `json:"server_name"`
	AddressFamily     AddressFamily     `json:"address_family"`
	MinimumTLSVersion MinimumTLSVersion `json:"minimum_tls_version"`
	ExpiryWarningDays int               `json:"expiry_warning_days"`
}

func DecodeConfiguration(raw json.RawMessage) (Configuration, error) {
	configuration, err := probe.DecodeConfigurationStrict[Configuration](raw)
	if err != nil {
		return Configuration{}, err
	}
	if configuration.SchemaVersion != ConfigurationSchemaVersion {
		return Configuration{}, errors.New("unsupported TLS configuration schema")
	}
	if configuration.Port == 0 {
		configuration.Port = 443
	}
	if configuration.Port < 1 || configuration.Port > 65535 {
		return Configuration{}, errors.New("TLS port is outside the valid range")
	}
	if configuration.ServerName != nil {
		normalized := strings.ToLower(strings.TrimSuffix(strings.TrimSpace(*configuration.ServerName), "."))
		if !validHostname(normalized) {
			return Configuration{}, errors.New("TLS server name is invalid")
		}
		configuration.ServerName = &normalized
	}
	if configuration.AddressFamily == "" {
		configuration.AddressFamily = AddressFamilyAuto
	}
	if configuration.AddressFamily != AddressFamilyAuto && configuration.AddressFamily != AddressFamilyIPv4 &&
		configuration.AddressFamily != AddressFamilyIPv6 {
		return Configuration{}, errors.New("TLS address family is invalid")
	}
	if configuration.MinimumTLSVersion == "" {
		configuration.MinimumTLSVersion = MinimumTLS12
	}
	if configuration.MinimumTLSVersion != MinimumTLS12 && configuration.MinimumTLSVersion != MinimumTLS13 {
		return Configuration{}, errors.New("TLS minimum version is invalid")
	}
	if configuration.ExpiryWarningDays < 0 || configuration.ExpiryWarningDays > 3650 {
		return Configuration{}, errors.New("TLS expiry warning days is outside the valid range")
	}
	return configuration, nil
}

func validHostname(value string) bool {
	if value == "" || len(value) > 253 || net.ParseIP(value) != nil {
		return false
	}
	for _, label := range strings.Split(value, ".") {
		if label == "" || len(label) > 63 || label[0] == '-' || label[len(label)-1] == '-' {
			return false
		}
		for _, character := range label {
			if !(character >= 'a' && character <= 'z') && !(character >= 'A' && character <= 'Z') &&
				!(character >= '0' && character <= '9') && character != '-' {
				return false
			}
		}
	}
	return true
}
