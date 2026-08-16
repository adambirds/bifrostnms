package dns

import (
	"context"
	"encoding/binary"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"strconv"
	"strings"
	"syscall"
	"time"

	"github.com/adambirds/bifrostnms/agent/probe"
	"golang.org/x/net/dns/dnsmessage"
)

type Answer struct {
	Type  string  `json:"type"`
	Name  string  `json:"name"`
	TTL   *uint32 `json:"ttl"`
	Value string  `json:"value"`
}

type Result struct {
	ResolverAddress *string  `json:"resolver_address"`
	QueryName       string   `json:"query_name"`
	QueryType       string   `json:"query_type"`
	ResponseCode    *string  `json:"response_code"`
	ResponseMS      *float64 `json:"response_ms"`
	AnswerCount     int      `json:"answer_count"`
	Answers         []Answer `json:"answers"`
	Truncated       bool     `json:"truncated"`
	Authoritative   bool     `json:"authoritative"`
	AssertionsTotal int      `json:"assertions_total"`
	AssertionsFailed int     `json:"assertions_failed"`
}

type Probe struct {
	resolver *net.Resolver
	now      func() time.Time
}

func New(resolver *net.Resolver) *Probe {
	if resolver == nil {
		resolver = net.DefaultResolver
	}
	return &Probe{resolver: resolver, now: time.Now}
}

func (*Probe) Type() probe.Type                   { return probe.TypeDNS }
func (*Probe) ConfigurationSchemaVersion() uint32 { return ConfigurationSchemaVersion }
func (*Probe) ResultSchemaVersion() uint32        { return ResultSchemaVersion }
func (*Probe) Validate(raw json.RawMessage) error { _, err := DecodeConfiguration(raw); return err }

func (p *Probe) Run(ctx context.Context, request probe.Request) probe.Result {
	startedAt := p.now()
	configuration, err := DecodeConfiguration(request.Configuration)
	if err != nil {
		return failed(startedAt.UTC(), p.now().UTC(), probe.ErrorInvalidConfiguration,
			"invalid_dns_configuration", "DNS configuration is invalid.")
	}
	queryName, err := effectiveQueryName(request.TargetAddress, configuration)
	if err != nil {
		return failed(startedAt.UTC(), p.now().UTC(), probe.ErrorInvalidConfiguration,
			"invalid_dns_query_name", "DNS query name is invalid.")
	}

	if configuration.ResolverMode == ResolverModeSystem {
		return p.runSystem(ctx, startedAt, queryName, configuration)
	}
	return p.runExplicit(ctx, startedAt, queryName, configuration)
}

func (p *Probe) runExplicit(
	ctx context.Context, startedAt time.Time, queryName string, configuration Configuration,
) probe.Result {
	message, err := buildQuery(queryName, configuration)
	if err != nil {
		return failed(startedAt.UTC(), p.now().UTC(), probe.ErrorInvalidConfiguration,
			"dns_query_build_failed", "DNS query could not be represented safely.")
	}
	resolver := net.JoinHostPort(*configuration.ResolverAddress, strconv.Itoa(configuration.ResolverPort))
	exchangeStarted := p.now()
	response, err := exchange(ctx, resolver, message, configuration.Transport)
	finishedAt := p.now()
	elapsed := milliseconds(finishedAt.Sub(exchangeStarted))
	base := Result{ResolverAddress: configuration.ResolverAddress, QueryName: queryName,
		QueryType: string(configuration.QueryType), ResponseMS: &elapsed, Answers: []Answer{}}
	if err != nil {
		classification := classifyExchangeError(ctx, err)
		if classification.failed {
			return failed(startedAt.UTC(), finishedAt.UTC(), classification.category,
				classification.code, classification.message)
		}
		return completedUnhealthy(startedAt.UTC(), finishedAt.UTC(), base, classification.category,
			classification.code, classification.message)
	}
	parsed, err := parseResponse(response, queryName, configuration.QueryType)
	if err != nil {
		return failed(startedAt.UTC(), finishedAt.UTC(), probe.ErrorProtocol,
			"dns_response_malformed", "DNS resolver returned a malformed or unsupported response.")
	}
	base.ResponseCode = &parsed.responseCode
	base.Answers = parsed.answers
	base.AnswerCount = len(parsed.answers)
	base.Truncated = parsed.truncated
	base.Authoritative = parsed.authoritative
	return assess(startedAt.UTC(), finishedAt.UTC(), base, configuration)
}

func (p *Probe) runSystem(
	ctx context.Context, startedAt time.Time, queryName string, configuration Configuration,
) probe.Result {
	lookupStarted := p.now()
	answers, err := p.systemLookup(ctx, queryName, configuration.QueryType)
	finishedAt := p.now()
	elapsed := milliseconds(finishedAt.Sub(lookupStarted))
	result := Result{QueryName: queryName, QueryType: string(configuration.QueryType),
		ResponseMS: &elapsed, Answers: answers, AnswerCount: len(answers)}
	if err != nil {
		var dnsError *net.DNSError
		if errors.As(err, &dnsError) && dnsError.IsNotFound {
			code := "NXDOMAIN"
			result.ResponseCode = &code
			return assess(startedAt.UTC(), finishedAt.UTC(), result, configuration)
		}
		classification := classifyExchangeError(ctx, err)
		if classification.failed {
			return failed(startedAt.UTC(), finishedAt.UTC(), classification.category,
				classification.code, classification.message)
		}
		return completedUnhealthy(startedAt.UTC(), finishedAt.UTC(), result, classification.category,
			classification.code, classification.message)
	}
	code := "NOERROR"
	result.ResponseCode = &code
	return assess(startedAt.UTC(), finishedAt.UTC(), result, configuration)
}

func (p *Probe) systemLookup(ctx context.Context, queryName string, queryType QueryType) ([]Answer, error) {
	answers := []Answer{}
	switch queryType {
	case QueryTypeA, QueryTypeAAAA:
		network := "ip4"
		if queryType == QueryTypeAAAA {
			network = "ip6"
		}
		addresses, err := p.resolver.LookupIP(ctx, network, queryName)
		if err != nil {
			return nil, err
		}
		for _, address := range addresses {
			answers = append(answers, Answer{Type: string(queryType), Name: queryName, Value: address.String()})
		}
	case QueryTypeCNAME:
		value, err := p.resolver.LookupCNAME(ctx, queryName)
		if err != nil {
			return nil, err
		}
		answers = append(answers, Answer{Type: "CNAME", Name: queryName, Value: normalizeName(value)})
	case QueryTypeMX:
		values, err := p.resolver.LookupMX(ctx, queryName)
		if err != nil {
			return nil, err
		}
		for _, value := range values {
			answers = append(answers, Answer{Type: "MX", Name: queryName,
				Value: fmt.Sprintf("%d %s", value.Pref, normalizeName(value.Host))})
		}
	case QueryTypeNS:
		values, err := p.resolver.LookupNS(ctx, queryName)
		if err != nil {
			return nil, err
		}
		for _, value := range values {
			answers = append(answers, Answer{Type: "NS", Name: queryName, Value: normalizeName(value.Host)})
		}
	case QueryTypeTXT:
		values, err := p.resolver.LookupTXT(ctx, queryName)
		if err != nil {
			return nil, err
		}
		for _, value := range values {
			answers = append(answers, Answer{Type: "TXT", Name: queryName, Value: value})
		}
	case QueryTypePTR:
		values, err := p.resolver.LookupAddr(ctx, queryName)
		if err != nil {
			return nil, err
		}
		for _, value := range values {
			answers = append(answers, Answer{Type: "PTR", Name: queryName, Value: normalizeName(value)})
		}
	}
	if len(answers) > MaximumAnswers {
		return nil, errors.New("DNS system resolver returned too many answers")
	}
	for _, answer := range answers {
		if len(answer.Value) > MaximumRecordBytes {
			return nil, errors.New("DNS system resolver returned an oversized answer")
		}
	}
	return answers, nil
}

type parsedResponse struct {
	responseCode  string
	answers       []Answer
	truncated     bool
	authoritative bool
}

func parseResponse(content []byte, queryName string, queryType QueryType) (parsedResponse, error) {
	if len(content) > MaximumMessageBytes {
		return parsedResponse{}, errors.New("DNS message exceeds limit")
	}
	var parser dnsmessage.Parser
	header, err := parser.Start(content)
	if err != nil || !header.Response {
		return parsedResponse{}, errors.New("invalid DNS response")
	}
	if _, err := parser.AllQuestions(); err != nil {
		return parsedResponse{}, err
	}
	resources, err := parser.AllAnswers()
	if err != nil {
		return parsedResponse{}, err
	}
	if len(resources) > MaximumAnswers {
		return parsedResponse{}, errors.New("DNS answer count exceeds limit")
	}
	answers := make([]Answer, 0, len(resources))
	for _, resource := range resources {
		answer, supported, err := normalizeResource(resource)
		if err != nil {
			return parsedResponse{}, err
		}
		if supported {
			answers = append(answers, answer)
		}
	}
	return parsedResponse{responseCode: responseCode(header.RCode), answers: answers,
		truncated: header.Truncated, authoritative: header.Authoritative}, nil
}

func normalizeResource(resource dnsmessage.Resource) (Answer, bool, error) {
	name := normalizeName(resource.Header.Name.String())
	ttl := resource.Header.TTL
	answer := Answer{Name: name, TTL: &ttl}
	switch body := resource.Body.(type) {
	case *dnsmessage.AResource:
		answer.Type, answer.Value = "A", net.IP(body.A[:]).String()
	case *dnsmessage.AAAAResource:
		answer.Type, answer.Value = "AAAA", net.IP(body.AAAA[:]).String()
	case *dnsmessage.CNAMEResource:
		answer.Type, answer.Value = "CNAME", normalizeName(body.CNAME.String())
	case *dnsmessage.MXResource:
		answer.Type = "MX"
		answer.Value = fmt.Sprintf("%d %s", body.Pref, normalizeName(body.MX.String()))
	case *dnsmessage.NSResource:
		answer.Type, answer.Value = "NS", normalizeName(body.NS.String())
	case *dnsmessage.PTRResource:
		answer.Type, answer.Value = "PTR", normalizeName(body.PTR.String())
	case *dnsmessage.TXTResource:
		answer.Type, answer.Value = "TXT", strings.Join(body.TXT, "")
	default:
		return Answer{}, false, nil
	}
	if len(answer.Value) > MaximumRecordBytes {
		return Answer{}, false, errors.New("DNS answer exceeds limit")
	}
	return answer, true, nil
}

func buildQuery(queryName string, configuration Configuration) ([]byte, error) {
	wireName := queryName
	if configuration.QueryType == QueryTypePTR {
		if address := net.ParseIP(queryName); address != nil {
			wireName = reverseAddress(address)
		}
	}
	name, err := dnsmessage.NewName(strings.TrimSuffix(wireName, ".") + ".")
	if err != nil {
		return nil, err
	}
	queryType, err := dnsMessageType(configuration.QueryType)
	if err != nil {
		return nil, err
	}
	builder := dnsmessage.NewBuilder(nil, dnsmessage.Header{ID: uint16(time.Now().UnixNano()),
		RecursionDesired: configuration.RecursionDesired})
	builder.EnableCompression()
	if err := builder.StartQuestions(); err != nil {
		return nil, err
	}
	if err := builder.Question(dnsmessage.Question{Name: name, Type: queryType, Class: dnsmessage.ClassINET}); err != nil {
		return nil, err
	}
	return builder.Finish()
}

func exchange(ctx context.Context, resolver string, query []byte, transport Transport) ([]byte, error) {
	if transport == TransportTCP {
		return exchangeTCP(ctx, resolver, query)
	}
	response, err := exchangeUDP(ctx, resolver, query)
	if err != nil {
		return nil, err
	}
	var parser dnsmessage.Parser
	header, err := parser.Start(response)
	if err != nil {
		return nil, err
	}
	if header.Truncated {
		return exchangeTCP(ctx, resolver, query)
	}
	return response, nil
}

func exchangeUDP(ctx context.Context, resolver string, query []byte) ([]byte, error) {
	connection, err := (&net.Dialer{}).DialContext(ctx, "udp", resolver)
	if err != nil {
		return nil, err
	}
	defer func() { _ = connection.Close() }()
	applyDeadline(ctx, connection)
	if _, err := connection.Write(query); err != nil {
		return nil, err
	}
	buffer := make([]byte, MaximumMessageBytes)
	count, err := connection.Read(buffer)
	if err != nil {
		return nil, err
	}
	return buffer[:count], nil
}

func exchangeTCP(ctx context.Context, resolver string, query []byte) ([]byte, error) {
	connection, err := (&net.Dialer{}).DialContext(ctx, "tcp", resolver)
	if err != nil {
		return nil, err
	}
	defer func() { _ = connection.Close() }()
	applyDeadline(ctx, connection)
	if len(query) > MaximumMessageBytes {
		return nil, errors.New("DNS query exceeds TCP message limit")
	}
	prefix := make([]byte, 2)
	binary.BigEndian.PutUint16(prefix, uint16(len(query)))
	if _, err := connection.Write(append(prefix, query...)); err != nil {
		return nil, err
	}
	if _, err := io.ReadFull(connection, prefix); err != nil {
		return nil, err
	}
	length := int(binary.BigEndian.Uint16(prefix))
	if length == 0 || length > MaximumMessageBytes {
		return nil, errors.New("DNS TCP response length is invalid")
	}
	response := make([]byte, length)
	if _, err := io.ReadFull(connection, response); err != nil {
		return nil, err
	}
	return response, nil
}

func applyDeadline(ctx context.Context, connection net.Conn) {
	if deadline, ok := ctx.Deadline(); ok {
		_ = connection.SetDeadline(deadline)
	}
}

func assess(startedAt, finishedAt time.Time, result Result, configuration Configuration) probe.Result {
	failedAssertions := 0
	if result.ResponseCode == nil || !containsString(configuration.ExpectedResponseCodes, *result.ResponseCode) {
		failedAssertions++
	}
	for _, expected := range configuration.ExpectedAnswers {
		matched := false
		for _, answer := range result.Answers {
			if answerMatches(configuration.QueryType, answer.Value, expected.Value) {
				matched = true
				break
			}
		}
		if !matched {
			failedAssertions++
		}
	}
	result.AssertionsTotal = 1 + len(configuration.ExpectedAnswers)
	result.AssertionsFailed = failedAssertions
	if failedAssertions > 0 {
		return completedUnhealthy(startedAt, finishedAt, result, probe.ErrorAssertion,
			"dns_assertion_failed", "One or more DNS assertions failed.")
	}
	return probe.Result{StartedAt: startedAt, FinishedAt: finishedAt,
		ExecutionStatus: probe.ExecutionCompleted, Assessment: probe.AssessmentHealthy, ProbeResult: result}
}

func effectiveQueryName(target string, configuration Configuration) (string, error) {
	value := target
	if configuration.QueryName != nil {
		value = *configuration.QueryName
	}
	value = strings.TrimSuffix(strings.TrimSpace(value), ".")
	if value == "" || len(value) > 253 || strings.ContainsAny(value, "\r\n\x00") {
		return "", errors.New("invalid DNS query name")
	}
	return value, nil
}

func dnsMessageType(queryType QueryType) (dnsmessage.Type, error) {
	switch queryType {
	case QueryTypeA:
		return dnsmessage.TypeA, nil
	case QueryTypeAAAA:
		return dnsmessage.TypeAAAA, nil
	case QueryTypeCNAME:
		return dnsmessage.TypeCNAME, nil
	case QueryTypeMX:
		return dnsmessage.TypeMX, nil
	case QueryTypeNS:
		return dnsmessage.TypeNS, nil
	case QueryTypeTXT:
		return dnsmessage.TypeTXT, nil
	case QueryTypePTR:
		return dnsmessage.TypePTR, nil
	default:
		return 0, errors.New("unsupported DNS query type")
	}
}

func responseCode(code dnsmessage.RCode) string {
	switch code {
	case dnsmessage.RCodeSuccess:
		return "NOERROR"
	case dnsmessage.RCodeFormatError:
		return "FORMERR"
	case dnsmessage.RCodeServerFailure:
		return "SERVFAIL"
	case dnsmessage.RCodeNameError:
		return "NXDOMAIN"
	case dnsmessage.RCodeNotImplemented:
		return "NOTIMP"
	case dnsmessage.RCodeRefused:
		return "REFUSED"
	default:
		return fmt.Sprintf("RCODE%d", code)
	}
}

func reverseAddress(address net.IP) string {
	if ipv4 := address.To4(); ipv4 != nil {
		return fmt.Sprintf("%d.%d.%d.%d.in-addr.arpa", ipv4[3], ipv4[2], ipv4[1], ipv4[0])
	}
	ipv6 := address.To16()
	parts := make([]string, 0, 32)
	for index := len(ipv6) - 1; index >= 0; index-- {
		parts = append(parts, fmt.Sprintf("%x", ipv6[index]&0x0f), fmt.Sprintf("%x", ipv6[index]>>4))
	}
	return strings.Join(parts, ".") + ".ip6.arpa"
}

func normalizeName(value string) string { return strings.TrimSuffix(strings.ToLower(value), ".") }

func answerMatches(queryType QueryType, actual, expected string) bool {
	switch queryType {
	case QueryTypeCNAME, QueryTypeNS, QueryTypePTR, QueryTypeMX:
		return strings.EqualFold(actual, expected)
	default:
		return actual == expected
	}
}

func containsString(values []string, expected string) bool {
	for _, value := range values {
		if value == expected {
			return true
		}
	}
	return false
}

func milliseconds(duration time.Duration) float64 {
	return float64(duration) / float64(time.Millisecond)
}

type errorClassification struct {
	category probe.ErrorCategory
	code     string
	message  string
	failed   bool
}

func classifyExchangeError(ctx context.Context, err error) errorClassification {
	if errors.Is(ctx.Err(), context.DeadlineExceeded) || errors.Is(err, context.DeadlineExceeded) {
		return errorClassification{category: probe.ErrorTimeout, code: "dns_resolver_timeout",
			message: "DNS resolver query timed out."}
	}
	if errors.Is(ctx.Err(), context.Canceled) || errors.Is(err, context.Canceled) {
		return errorClassification{category: probe.ErrorInternal, code: "dns_cancelled",
			message: "DNS query was cancelled locally.", failed: true}
	}
	if errors.Is(err, syscall.EMFILE) || errors.Is(err, syscall.ENFILE) ||
		errors.Is(err, syscall.ENOBUFS) || errors.Is(err, syscall.ENOMEM) {
		return errorClassification{category: probe.ErrorResourceLimit, code: "dns_local_resource_exhausted",
			message: "DNS query could not start because local resources are exhausted.", failed: true}
	}
	var netError net.Error
	if errors.As(err, &netError) && netError.Timeout() {
		return errorClassification{category: probe.ErrorTimeout, code: "dns_resolver_timeout",
			message: "DNS resolver query timed out."}
	}
	return errorClassification{category: probe.ErrorConnection, code: "dns_resolver_unreachable",
		message: "DNS resolver could not be reached."}
}

func completedUnhealthy(
	startedAt, finishedAt time.Time, result Result, category probe.ErrorCategory, code, message string,
) probe.Result {
	return probe.Result{StartedAt: startedAt, FinishedAt: finishedAt,
		ExecutionStatus: probe.ExecutionCompleted, Assessment: probe.AssessmentUnhealthy,
		ErrorCategory: &category, ErrorCode: code, ErrorMessage: message, ProbeResult: result}
}

func failed(
	startedAt, finishedAt time.Time, category probe.ErrorCategory, code, message string,
) probe.Result {
	return probe.Result{StartedAt: startedAt, FinishedAt: finishedAt,
		ExecutionStatus: probe.ExecutionFailed, Assessment: probe.AssessmentUnknown,
		ErrorCategory: &category, ErrorCode: code, ErrorMessage: message}
}
