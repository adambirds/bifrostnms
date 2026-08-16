package tcp

import (
	"encoding/json"
	"errors"

	"github.com/adambirds/bifrostnms/agent/probe"
)

const (
	ConfigurationSchemaVersion uint32 = 1
	ResultSchemaVersion        uint32 = 1
)

type AddressFamily string

const (
	AddressFamilyAuto AddressFamily = "auto"
	AddressFamilyIPv4 AddressFamily = "ipv4"
	AddressFamilyIPv6 AddressFamily = "ipv6"
)

type Configuration struct {
	SchemaVersion uint32        `json:"schema_version"`
	Port          int           `json:"port"`
	AddressFamily AddressFamily `json:"address_family"`
}

func DecodeConfiguration(raw json.RawMessage) (Configuration, error) {
	configuration, err := probe.DecodeConfigurationStrict[Configuration](raw)
	if err != nil {
		return Configuration{}, err
	}
	if configuration.SchemaVersion != ConfigurationSchemaVersion {
		return Configuration{}, errors.New("unsupported TCP configuration schema")
	}
	if configuration.Port < 1 || configuration.Port > 65535 {
		return Configuration{}, errors.New("TCP port is outside the valid range")
	}
	if configuration.AddressFamily == "" {
		configuration.AddressFamily = AddressFamilyAuto
	}
	if configuration.AddressFamily != AddressFamilyAuto &&
		configuration.AddressFamily != AddressFamilyIPv4 &&
		configuration.AddressFamily != AddressFamilyIPv6 {
		return Configuration{}, errors.New("TCP address family is invalid")
	}
	return configuration, nil
}
