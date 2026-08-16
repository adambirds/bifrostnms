package synchronization

import (
	"bytes"
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"github.com/adambirds/bifrostnms/agent/probe"
	"github.com/adambirds/bifrostnms/agent/protocol"
	"github.com/adambirds/bifrostnms/agent/storage"
)

const maximumControlResponseBytes = 2 << 20

type ControlPlane struct {
	HTTPClient *http.Client
}

func (c *ControlPlane) SynchronizeConfiguration(
	ctx context.Context, store *storage.Store, registry *probe.Registry,
	capabilities protocol.Capabilities, now time.Time,
) (bool, error) {
	identity, credential, err := synchronizationIdentity(ctx, store)
	if err != nil {
		return false, err
	}
	activeRevision := int64(0)
	activeHash := ""
	active, err := store.ActiveConfiguration(ctx)
	if err == nil {
		activeRevision = active.Revision
		activeHash = "sha256:" + active.ContentHash
	} else if !errors.Is(err, sql.ErrNoRows) {
		return false, fmt.Errorf("read active configuration: %w", err)
	}
	configuration, err := c.Configuration(
		ctx, identity, credential, activeRevision, activeHash,
	)
	if err != nil {
		return false, err
	}
	if configuration == nil {
		if activeRevision == 0 || active.ActivatedAt == nil {
			return false, nil
		}
		return false, c.AcknowledgeConfiguration(ctx, identity, credential,
			protocol.ConfigurationAcknowledgement{
				ProtocolVersion: protocol.Version, Revision: active.Revision,
				ContentHash: activeHash, ActivatedAt: *active.ActivatedAt,
			})
	}
	canonical, err := configuration.Validate(identity.AgentID, identity.RealmID, capabilities)
	if err != nil {
		return false, fmt.Errorf("validate desired configuration: %w", err)
	}
	for _, monitor := range configuration.Monitors {
		raw, marshalErr := json.Marshal(monitor.Configuration)
		if marshalErr != nil {
			return false, fmt.Errorf("encode monitor configuration: %w", marshalErr)
		}
		if validateErr := registry.Validate(
			probe.Type(monitor.ProbeType), uint32(monitor.ProbeSchemaVersion), raw,
		); validateErr != nil {
			return false, fmt.Errorf("validate monitor %s: %w", monitor.MonitorID, validateErr)
		}
	}
	digest := strings.TrimPrefix(strings.ToLower(configuration.ContentHash), "sha256:")
	activatedAt := now.UTC()
	if err := store.ActivateConfiguration(ctx, storage.ConfigurationSnapshot{
		Revision: configuration.Revision, ContentHash: digest,
		SchemaVersion:    configuration.ConfigurationSchemaVersion,
		CanonicalPayload: canonical, DownloadedAt: activatedAt,
		ValidatedAt: &activatedAt, ActivatedAt: &activatedAt,
	}); err != nil {
		return false, fmt.Errorf("activate desired configuration: %w", err)
	}
	if err := c.AcknowledgeConfiguration(ctx, identity, credential,
		protocol.ConfigurationAcknowledgement{
			ProtocolVersion: protocol.Version, Revision: configuration.Revision,
			ContentHash: configuration.ContentHash, ActivatedAt: activatedAt,
		}); err != nil {
		return true, fmt.Errorf("acknowledge active configuration: %w", err)
	}
	return true, nil
}

func synchronizationIdentity(
	ctx context.Context, store *storage.Store,
) (storage.Identity, storage.Credential, error) {
	identity, err := store.Identity(ctx)
	if err != nil {
		return storage.Identity{}, storage.Credential{}, fmt.Errorf("read agent identity: %w", err)
	}
	credentials, err := store.Credentials(ctx)
	if err != nil {
		return storage.Identity{}, storage.Credential{}, fmt.Errorf("read agent credentials: %w", err)
	}
	if len(credentials) == 0 {
		return storage.Identity{}, storage.Credential{}, errors.New("no agent credential is available")
	}
	return identity, credentials[len(credentials)-1], nil
}

func (c *ControlPlane) Enrol(
	ctx context.Context, controlPlaneURL string, request protocol.EnrolmentRequest,
) (protocol.EnrolmentResponse, error) {
	var response protocol.EnrolmentResponse
	err := c.doJSON(ctx, http.MethodPost, endpoint(controlPlaneURL, "/api/v1/agent/enrol"),
		"", request, &response)
	if err != nil {
		return protocol.EnrolmentResponse{}, err
	}
	if response.ProtocolVersion != protocol.Version || response.AgentID == "" ||
		response.RealmID == "" || response.CredentialID == "" || response.Credential == "" {
		return protocol.EnrolmentResponse{}, errors.New("enrolment response is incomplete")
	}
	return response, nil
}

func (c *ControlPlane) Heartbeat(
	ctx context.Context, identity storage.Identity, credential storage.Credential,
	request protocol.HeartbeatRequest,
) (protocol.HeartbeatResponse, error) {
	var response protocol.HeartbeatResponse
	err := c.doJSON(ctx, http.MethodPost, endpoint(identity.ControlPlaneURL,
		"/api/v1/agent/heartbeat"), bearer(credential), request, &response)
	if err != nil {
		return protocol.HeartbeatResponse{}, err
	}
	if response.ProtocolVersion != protocol.Version ||
		response.MinimumProtocolVersion > protocol.Version ||
		response.MaximumProtocolVersion < protocol.Version {
		return protocol.HeartbeatResponse{}, errors.New("heartbeat protocol is incompatible")
	}
	return response, nil
}

func (c *ControlPlane) Configuration(
	ctx context.Context, identity storage.Identity, credential storage.Credential,
	activeRevision int64, contentHash string,
) (*protocol.ConfigurationResponse, error) {
	location, err := url.Parse(endpoint(identity.ControlPlaneURL, "/api/v1/agent/config"))
	if err != nil {
		return nil, fmt.Errorf("parse configuration endpoint: %w", err)
	}
	query := location.Query()
	query.Set("protocol_version", strconv.Itoa(protocol.Version))
	query.Set("active_revision", strconv.FormatInt(activeRevision, 10))
	if contentHash != "" {
		query.Set("content_hash", contentHash)
	}
	location.RawQuery = query.Encode()
	httpRequest, err := http.NewRequestWithContext(ctx, http.MethodGet, location.String(), nil)
	if err != nil {
		return nil, fmt.Errorf("create configuration request: %w", err)
	}
	httpRequest.Header.Set("Authorization", bearer(credential))
	response, err := c.httpClient().Do(httpRequest)
	if err != nil {
		return nil, fmt.Errorf("request configuration: %w", err)
	}
	defer func() { _ = response.Body.Close() }()
	if response.StatusCode == http.StatusNotModified {
		return nil, nil
	}
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return nil, responseError(response)
	}
	var configuration protocol.ConfigurationResponse
	if err := decodeJSON(response.Body, &configuration); err != nil {
		return nil, fmt.Errorf("decode configuration response: %w", err)
	}
	return &configuration, nil
}

func (c *ControlPlane) AcknowledgeConfiguration(
	ctx context.Context, identity storage.Identity, credential storage.Credential,
	acknowledgement protocol.ConfigurationAcknowledgement,
) error {
	var response struct {
		ProtocolVersion         int    `json:"protocol_version"`
		AcknowledgedRevision    int64  `json:"acknowledged_revision"`
		AcknowledgedContentHash string `json:"acknowledged_content_hash"`
	}
	if err := c.doJSON(ctx, http.MethodPost, endpoint(identity.ControlPlaneURL,
		"/api/v1/agent/config/acknowledge"), bearer(credential), acknowledgement,
		&response); err != nil {
		return err
	}
	if response.ProtocolVersion != protocol.Version ||
		response.AcknowledgedRevision != acknowledgement.Revision ||
		!strings.EqualFold(response.AcknowledgedContentHash, acknowledgement.ContentHash) {
		return errors.New("configuration acknowledgement response does not match")
	}
	return nil
}

func (c *ControlPlane) doJSON(
	ctx context.Context, method string, location string, authorization string,
	body any, destination any,
) error {
	encoded, err := json.Marshal(body)
	if err != nil {
		return fmt.Errorf("encode request: %w", err)
	}
	request, err := http.NewRequestWithContext(ctx, method, location, bytes.NewReader(encoded))
	if err != nil {
		return fmt.Errorf("create request: %w", err)
	}
	request.Header.Set("Content-Type", "application/json")
	if authorization != "" {
		request.Header.Set("Authorization", authorization)
	}
	response, err := c.httpClient().Do(request)
	if err != nil {
		return fmt.Errorf("send request: %w", err)
	}
	defer func() { _ = response.Body.Close() }()
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return responseError(response)
	}
	if err := decodeJSON(response.Body, destination); err != nil {
		return fmt.Errorf("decode response: %w", err)
	}
	return nil
}

func (c *ControlPlane) httpClient() *http.Client {
	if c.HTTPClient != nil {
		return c.HTTPClient
	}
	return &http.Client{Timeout: 30 * time.Second}
}

func endpoint(base string, path string) string { return strings.TrimRight(base, "/") + path }

func bearer(credential storage.Credential) string {
	return "Bearer " + credential.CredentialID + "." + credential.Secret
}

func decodeJSON(reader io.Reader, destination any) error {
	decoder := json.NewDecoder(io.LimitReader(reader, maximumControlResponseBytes+1))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(destination); err != nil {
		return err
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		return errors.New("response has trailing data")
	}
	return nil
}

func responseError(response *http.Response) error {
	var payload protocol.ErrorResponse
	if err := decodeJSON(response.Body, &payload); err == nil && payload.Error.Code != "" {
		return fmt.Errorf("control plane returned %s: %s", payload.Error.Code, payload.Error.Message)
	}
	return fmt.Errorf("control plane returned %s", response.Status)
}
