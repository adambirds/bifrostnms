package http

import (
	"encoding/json"
	"errors"
	"fmt"
	"net"
	"net/textproto"
	"strings"
	"unicode"

	"github.com/adambirds/bifrostnms/agent/probe"
)

const (
	ConfigurationSchemaVersion  uint32 = 1
	ResultSchemaVersion         uint32 = 1
	DefaultMaximumResponseBytes        = 1 << 20
	MaximumResponseBytes               = 4 << 20
)

type AddressFamily string

const (
	AddressFamilyAuto AddressFamily = "auto"
	AddressFamilyIPv4 AddressFamily = "ipv4"
	AddressFamilyIPv6 AddressFamily = "ipv6"
)

type HeaderAssertion struct {
	Name  string `json:"name"`
	Value string `json:"value"`
}

type Configuration struct {
	SchemaVersion        uint32            `json:"schema_version"`
	Scheme               string            `json:"scheme"`
	Port                 *int              `json:"port"`
	Path                 string            `json:"path"`
	Method               string            `json:"method"`
	FollowRedirects      bool              `json:"follow_redirects"`
	MaximumRedirects     int               `json:"maximum_redirects"`
	HostHeader           *string           `json:"host_header"`
	RequestHeaders       map[string]string `json:"request_headers"`
	ExpectedStatusCodes  []int             `json:"expected_status_codes"`
	ExpectedHeaderValues []HeaderAssertion `json:"expected_header_values"`
	ExpectedBodyContains []string          `json:"expected_body_contains"`
	MaximumResponseBytes int               `json:"maximum_response_bytes"`
	AddressFamily        AddressFamily     `json:"address_family"`
}

var forbiddenHeaders = map[string]struct{}{
	"Authorization":       {},
	"Cookie":              {},
	"Proxy-Authorization": {},
}

func DecodeConfiguration(raw json.RawMessage) (Configuration, error) {
	configuration, err := probe.DecodeConfigurationStrict[Configuration](raw)
	if err != nil {
		return Configuration{}, err
	}
	if configuration.SchemaVersion != ConfigurationSchemaVersion {
		return Configuration{}, errors.New("unsupported HTTP configuration schema")
	}
	if configuration.Scheme == "" {
		configuration.Scheme = "https"
	}
	if configuration.Scheme != "http" && configuration.Scheme != "https" {
		return Configuration{}, errors.New("HTTP scheme is invalid")
	}
	if configuration.Method == "" {
		configuration.Method = "GET"
	}
	if configuration.Method != "GET" && configuration.Method != "HEAD" {
		return Configuration{}, errors.New("HTTP method is invalid")
	}
	if configuration.Path == "" {
		configuration.Path = "/"
	}
	if !strings.HasPrefix(configuration.Path, "/") || containsControl(configuration.Path) {
		return Configuration{}, errors.New("HTTP path is invalid")
	}
	if configuration.Port != nil && (*configuration.Port < 1 || *configuration.Port > 65535) {
		return Configuration{}, errors.New("HTTP port is outside the valid range")
	}
	if configuration.MaximumRedirects == 0 {
		configuration.MaximumRedirects = 5
	}
	if configuration.MaximumRedirects < 0 || configuration.MaximumRedirects > 10 {
		return Configuration{}, errors.New("HTTP maximum redirects is outside the valid range")
	}
	if configuration.HostHeader != nil && !validHostname(*configuration.HostHeader) {
		return Configuration{}, errors.New("HTTP host header is invalid")
	}
	if len(configuration.RequestHeaders) > 32 {
		return Configuration{}, errors.New("HTTP request header count exceeds the valid range")
	}
	for name, value := range configuration.RequestHeaders {
		canonical := textproto.CanonicalMIMEHeaderKey(name)
		if !validHeaderName(name) || len(value) > 1024 || containsControl(value) {
			return Configuration{}, errors.New("HTTP request header is invalid")
		}
		if _, forbidden := forbiddenHeaders[canonical]; forbidden {
			return Configuration{}, fmt.Errorf("HTTP request header %q is not permitted", canonical)
		}
	}
	if len(configuration.ExpectedStatusCodes) == 0 {
		configuration.ExpectedStatusCodes = make([]int, 200)
		for index := range configuration.ExpectedStatusCodes {
			configuration.ExpectedStatusCodes[index] = 200 + index
		}
	}
	if len(configuration.ExpectedStatusCodes) > 200 {
		return Configuration{}, errors.New("HTTP expected status code count exceeds the valid range")
	}
	seenStatus := make(map[int]struct{}, len(configuration.ExpectedStatusCodes))
	for _, status := range configuration.ExpectedStatusCodes {
		if status < 100 || status > 599 {
			return Configuration{}, errors.New("HTTP expected status code is invalid")
		}
		if _, duplicate := seenStatus[status]; duplicate {
			return Configuration{}, errors.New("HTTP expected status codes must be unique")
		}
		seenStatus[status] = struct{}{}
	}
	if len(configuration.ExpectedHeaderValues) > 32 {
		return Configuration{}, errors.New("HTTP header assertion count exceeds the valid range")
	}
	for _, assertion := range configuration.ExpectedHeaderValues {
		if !validHeaderName(assertion.Name) || len(assertion.Value) > 1024 || containsControl(assertion.Value) {
			return Configuration{}, errors.New("HTTP header assertion is invalid")
		}
	}
	if len(configuration.ExpectedBodyContains) > 16 {
		return Configuration{}, errors.New("HTTP body assertion count exceeds the valid range")
	}
	for _, expected := range configuration.ExpectedBodyContains {
		if expected == "" || len(expected) > 1024 || containsControl(expected) {
			return Configuration{}, errors.New("HTTP body assertion is invalid")
		}
	}
	if configuration.Method == "HEAD" && len(configuration.ExpectedBodyContains) > 0 {
		return Configuration{}, errors.New("HTTP HEAD monitors cannot contain body assertions")
	}
	if configuration.MaximumResponseBytes == 0 {
		configuration.MaximumResponseBytes = DefaultMaximumResponseBytes
	}
	if configuration.MaximumResponseBytes < 1 || configuration.MaximumResponseBytes > MaximumResponseBytes {
		return Configuration{}, errors.New("HTTP maximum response bytes is outside the valid range")
	}
	if configuration.AddressFamily == "" {
		configuration.AddressFamily = AddressFamilyAuto
	}
	if configuration.AddressFamily != AddressFamilyAuto &&
		configuration.AddressFamily != AddressFamilyIPv4 &&
		configuration.AddressFamily != AddressFamilyIPv6 {
		return Configuration{}, errors.New("HTTP address family is invalid")
	}
	return configuration, nil
}

func containsControl(value string) bool {
	return strings.IndexFunc(value, unicode.IsControl) >= 0
}

func validHeaderName(value string) bool {
	if value == "" {
		return false
	}
	for _, character := range value {
		if !(character >= 'a' && character <= 'z') &&
			!(character >= 'A' && character <= 'Z') &&
			!(character >= '0' && character <= '9') && !strings.ContainsRune("!#$%&'*+-.^_`|~", character) {
			return false
		}
	}
	return true
}

func validHostname(value string) bool {
	if value == "" || len(value) > 253 || containsControl(value) || net.ParseIP(value) != nil {
		return false
	}
	value = strings.TrimSuffix(value, ".")
	labels := strings.Split(value, ".")
	for _, label := range labels {
		if label == "" || len(label) > 63 || label[0] == '-' || label[len(label)-1] == '-' {
			return false
		}
		for _, character := range label {
			if !(character >= 'a' && character <= 'z') &&
				!(character >= 'A' && character <= 'Z') &&
				!(character >= '0' && character <= '9') && character != '-' {
				return false
			}
		}
	}
	return true
}
