package synchronization

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math/rand/v2"
	"net/http"
	"strings"
	"time"

	"github.com/adambirds/bifrostnms/agent/protocol"
	"github.com/adambirds/bifrostnms/agent/storage"
)

var (
	ErrBackoffActive = errors.New("observation upload backoff is active")
	ErrNoReadyData   = errors.New("no observations are ready to upload")
)

type Client struct {
	Store      *storage.Store
	HTTPClient *http.Client
	Now        func() time.Time
	Random     func() float64
}

func (c *Client) UploadOnce(ctx context.Context) (int, error) {
	now := c.now()
	state, err := c.Store.SynchronizationState(ctx)
	if err != nil {
		return 0, err
	}
	if state.ServerBackoffUntil != nil && now.Before(*state.ServerBackoffUntil) {
		return 0, ErrBackoffActive
	}
	batch, err := BuildBatch(
		ctx, c.Store, now, DefaultMaxBatchObservations, DefaultMaxBatchBytes,
	)
	if err != nil {
		var oversized *OversizedObservationError
		if errors.As(err, &oversized) {
			quarantineErr := c.Store.QuarantineObservation(
				ctx, oversized.Observation, "local_payload_too_large",
				"serialized upload exceeds 1 MiB", now,
			)
			return 0, quarantineErr
		}
		var invalid *InvalidObservationError
		if errors.As(err, &invalid) {
			quarantineErr := c.Store.QuarantineObservation(
				ctx, invalid.Observation, "local_invalid_payload",
				"stored observation is not valid JSON", now,
			)
			return 0, quarantineErr
		}
		return 0, err
	}
	if len(batch.Observations) == 0 {
		return 0, ErrNoReadyData
	}
	identity, err := c.Store.Identity(ctx)
	if err != nil {
		return 0, fmt.Errorf("read upload identity: %w", err)
	}
	credentials, err := c.Store.Credentials(ctx)
	if err != nil {
		return 0, fmt.Errorf("read upload credential: %w", err)
	}
	if len(credentials) == 0 {
		return 0, errors.New("no upload credential is available")
	}
	credential := credentials[len(credentials)-1]
	request, err := http.NewRequestWithContext(
		ctx, http.MethodPost,
		strings.TrimRight(identity.ControlPlaneURL, "/")+"/api/v1/agent/observations",
		bytes.NewReader(batch.Body),
	)
	if err != nil {
		return 0, fmt.Errorf("create observation upload request: %w", err)
	}
	request.Header.Set("Authorization", "Bearer "+credential.CredentialID+"."+credential.Secret)
	request.Header.Set("Content-Type", "application/json")
	response, err := c.httpClient().Do(request)
	if err != nil {
		return 0, c.recordFailure(ctx, state, 0, fmt.Errorf("upload observations: %w", err))
	}
	defer func() { _ = response.Body.Close() }()
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		_, _ = io.Copy(io.Discard, io.LimitReader(response.Body, 4096))
		return 0, c.recordFailure(
			ctx, state, retryAfter(response), fmt.Errorf("observation upload returned %s", response.Status),
		)
	}
	var acknowledgement protocol.ObservationUploadResponse
	decoder := json.NewDecoder(io.LimitReader(response.Body, DefaultMaxBatchBytes+1))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&acknowledgement); err != nil {
		return 0, c.recordFailure(ctx, state, 0, fmt.Errorf("decode upload response: %w", err))
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		return 0, c.recordFailure(ctx, state, 0, errors.New("upload response has trailing data"))
	}
	if acknowledgement.ProtocolVersion != protocol.Version ||
		acknowledgement.BatchID != batch.Upload.BatchID {
		return 0, c.recordFailure(ctx, state, 0, storage.ErrUntrustedAcknowledgement)
	}
	serverDelay := time.Duration(0)
	if acknowledgement.RetryAfterSeconds != nil {
		serverDelay = time.Duration(*acknowledgement.RetryAfterSeconds) * time.Second
	}
	results := make([]storage.ObservationAcknowledgement, len(acknowledgement.Results))
	for index, result := range acknowledgement.Results {
		nextAttempt := time.Time{}
		if result.Retryable && index < len(batch.Observations) {
			delay := RetryDelay(
				batch.Observations[index].AttemptCount+1, serverDelay, c.randomFraction(),
			)
			nextAttempt = now.Add(delay)
		}
		results[index] = storage.ObservationAcknowledgement{
			ScheduledAt: result.ScheduledAt, ObservationID: result.ObservationID,
			Disposition: storage.ObservationDisposition(result.Disposition),
			Code:        result.Code, Retryable: result.Retryable, NextAttemptAt: nextAttempt,
		}
	}
	if err := c.Store.ApplyAcknowledgements(ctx, batch.Observations, results, now); err != nil {
		return 0, c.recordFailure(ctx, state, serverDelay, err)
	}
	return len(batch.Observations), nil
}

func (c *Client) recordFailure(
	ctx context.Context, state storage.SynchronizationState, serverDelay time.Duration, cause error,
) error {
	delay := RetryDelay(state.ConsecutiveFailureCount+1, serverDelay, c.randomFraction())
	if err := c.Store.RecordSynchronizationFailure(ctx, c.now().Add(delay)); err != nil {
		return errors.Join(cause, err)
	}
	return cause
}

func (c *Client) now() time.Time {
	if c.Now != nil {
		return c.Now().UTC()
	}
	return time.Now().UTC()
}

func (c *Client) randomFraction() float64 {
	if c.Random != nil {
		return c.Random()
	}
	return rand.Float64()
}

func (c *Client) httpClient() *http.Client {
	if c.HTTPClient != nil {
		return c.HTTPClient
	}
	return http.DefaultClient
}

func retryAfter(response *http.Response) time.Duration {
	value := response.Header.Get("Retry-After")
	parsed, err := time.ParseDuration(value + "s")
	if err != nil {
		return 0
	}
	return parsed
}
