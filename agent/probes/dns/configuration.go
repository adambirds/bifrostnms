package dns

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
	MaximumAnswers                    = 100
	MaximumRecordBytes                = 1024
	MaximumMessageBytes               = 65535
)

type ResolverMode string

type Transport string

type QueryType string

const (
	ResolverModeSystem   ResolverMode = "system"
	ResolverModeExplicit ResolverMode = "explicit"

	TransportUDPWithTCPFallback Transport = "udp_with_tcp_fallback"
	TransportTCP                Transport = "tcp"

	QueryTypeA     QueryType = "A"
	QueryTypeAAAA  QueryType = "AAAA"
	QueryTypeCNAME QueryType = "CNAME"
	QueryTypeMX    QueryType = "MX"
	QueryTypeNS    QueryType = "NS"
	QueryTypeTXT   QueryType = "TXT"
	QueryTypePTR   QueryType = "PTR"
)

type AnswerAssertion struct {
	Value string `json:"value"`
}

type Configuration struct {
	SchemaVersion         uint32            `json:"schema_version"`
	ResolverMode          ResolverMode      `json:"resolver_mode"`
	ResolverAddress       *string           `json:"resolver_address"`
	ResolverPort          int               `json:"resolver_port"`
	Transport             Transport         `json:"transport"`
	QueryName             *string           `json:"query_name"`
	QueryType             QueryType         `json:"query_type"`
	RecursionDesired      bool              `json:"recursion_desired"`
	ExpectedResponseCodes []string          `json:"expected_response_codes"`
	ExpectedAnswers       []AnswerAssertion `json:"expected_answers"`
}

func DecodeConfiguration(raw json.RawMessage) (Configuration, error) {
	configuration, err := probe.DecodeConfigurationStrict[Configuration](raw)
	if err != nil {
		return Configuration{}, err
	}
	if configuration.SchemaVersion != ConfigurationSchemaVersion {
		return Configuration{}, errors.New("unsupported DNS configuration schema")
	}
	if configuration.ResolverMode == "" {
		configuration.ResolverMode = ResolverModeSystem
	}
	if configuration.ResolverMode != ResolverModeSystem && configuration.ResolverMode != ResolverModeExplicit {
		return Configuration{}, errors.New("DNS resolver mode is invalid")
	}
	if configuration.ResolverPort == 0 {
		configuration.ResolverPort = 53
	}
	if configuration.ResolverPort < 1 || configuration.ResolverPort > 65535 {
		return Configuration{}, errors.New("DNS resolver port is outside the valid range")
	}
	if configuration.Transport == "" {
		configuration.Transport = TransportUDPWithTCPFallback
	}
	if configuration.Transport != TransportUDPWithTCPFallback && configuration.Transport != TransportTCP {
		return Configuration{}, errors.New("DNS transport is invalid")
	}
	if configuration.ResolverMode == ResolverModeExplicit {
		if configuration.ResolverAddress == nil || net.ParseIP(*configuration.ResolverAddress) == nil {
			return Configuration{}, errors.New("explicit DNS resolver address must be an IP address")
		}
	} else {
		if configuration.ResolverAddress != nil {
			return Configuration{}, errors.New("system DNS resolver mode cannot specify an explicit resolver")
		}
		if configuration.Transport != TransportUDPWithTCPFallback {
			return Configuration{}, errors.New("system DNS resolver mode uses platform resolver transport behavior")
		}
	}
	if configuration.QueryName != nil {
		normalized := strings.TrimSuffix(strings.TrimSpace(*configuration.QueryName), ".")
		if normalized == "" || len(normalized) > 253 || strings.ContainsAny(normalized, "\r\n\x00") {
			return Configuration{}, errors.New("DNS query name is invalid")
		}
		configuration.QueryName = &normalized
	}
	switch configuration.QueryType {
	case QueryTypeA, QueryTypeAAAA, QueryTypeCNAME, QueryTypeMX, QueryTypeNS, QueryTypeTXT, QueryTypePTR:
	default:
		return Configuration{}, errors.New("DNS query type is invalid")
	}
	if len(configuration.ExpectedResponseCodes) == 0 {
		configuration.ExpectedResponseCodes = []string{"NOERROR"}
	}
	if len(configuration.ExpectedResponseCodes) > 16 {
		return Configuration{}, errors.New("DNS expected response code count exceeds the valid range")
	}
	seenCodes := make(map[string]struct{}, len(configuration.ExpectedResponseCodes))
	for index, code := range configuration.ExpectedResponseCodes {
		code = strings.ToUpper(strings.TrimSpace(code))
		if !validResponseCode(code) {
			return Configuration{}, errors.New("DNS expected response code is invalid")
		}
		if _, exists := seenCodes[code]; exists {
			return Configuration{}, errors.New("DNS expected response codes must be unique")
		}
		seenCodes[code] = struct{}{}
		configuration.ExpectedResponseCodes[index] = code
	}
	if len(configuration.ExpectedAnswers) > 32 {
		return Configuration{}, errors.New("DNS answer assertion count exceeds the valid range")
	}
	for _, assertion := range configuration.ExpectedAnswers {
		if assertion.Value == "" || len(assertion.Value) > MaximumRecordBytes || strings.ContainsAny(assertion.Value, "\r\n\x00") {
			return Configuration{}, errors.New("DNS answer assertion is invalid")
		}
	}
	return configuration, nil
}

func validResponseCode(code string) bool {
	switch code {
	case "NOERROR", "FORMERR", "SERVFAIL", "NXDOMAIN", "NOTIMP", "REFUSED":
		return true
	default:
		return false
	}
}
