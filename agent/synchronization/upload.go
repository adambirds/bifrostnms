package synchronization

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"time"

	"github.com/adambirds/bifrostnms/agent/protocol"
	"github.com/adambirds/bifrostnms/agent/storage"
)

const (
	DefaultMaxBatchObservations = 500
	DefaultMaxBatchBytes        = 1 << 20
	InitialRetryDelay           = time.Second
	MaximumRetryDelay           = 5 * time.Minute
)

var ErrObservationTooLarge = errors.New("observation exceeds upload batch limit")

var ErrInvalidObservation = errors.New("observation payload is not valid JSON")

type OversizedObservationError struct {
	Observation storage.Observation
}

func (e *OversizedObservationError) Error() string { return ErrObservationTooLarge.Error() }
func (e *OversizedObservationError) Unwrap() error { return ErrObservationTooLarge }

type InvalidObservationError struct {
	Observation storage.Observation
}

func (e *InvalidObservationError) Error() string { return ErrInvalidObservation.Error() }
func (e *InvalidObservationError) Unwrap() error { return ErrInvalidObservation }

type Batch struct {
	Upload       protocol.ObservationUpload
	Observations []storage.Observation
	Body         []byte
}

func BuildBatch(
	ctx context.Context,
	store *storage.Store,
	now time.Time,
	maxObservations int,
	maxBytes int,
) (Batch, error) {
	if maxObservations < 1 || maxBytes < 1 {
		return Batch{}, errors.New("positive upload batch limits are required")
	}
	ready, err := store.ReadyObservations(ctx, now, maxObservations+1)
	if err != nil || len(ready) == 0 {
		return Batch{}, err
	}
	batchID, err := newBatchID()
	if err != nil {
		return Batch{}, err
	}
	upload := protocol.ObservationUpload{
		ProtocolVersion:     protocol.Version,
		ResultSchemaVersion: 1,
		AgentConfigRevision: ready[0].AgentConfigRevision,
		BatchID:             batchID,
	}
	selected := make([]storage.Observation, 0, maxObservations)
	var body []byte
	for _, observation := range ready {
		if len(selected) == maxObservations ||
			observation.AgentConfigRevision != upload.AgentConfigRevision {
			break
		}
		if !json.Valid(observation.CanonicalPayload) {
			return Batch{}, &InvalidObservationError{Observation: observation}
		}
		upload.Observations = append(upload.Observations, observation.CanonicalPayload)
		candidate, marshalErr := json.Marshal(upload)
		if marshalErr != nil {
			return Batch{}, fmt.Errorf("encode observation upload: %w", marshalErr)
		}
		if len(candidate) > maxBytes {
			upload.Observations = upload.Observations[:len(upload.Observations)-1]
			if len(selected) == 0 {
				return Batch{}, &OversizedObservationError{Observation: observation}
			}
			break
		}
		selected = append(selected, observation)
		body = candidate
	}
	return Batch{Upload: upload, Observations: selected, Body: body}, nil
}

func RetryDelay(failureCount int, serverRetryAfter time.Duration, randomFraction float64) time.Duration {
	if failureCount < 1 {
		failureCount = 1
	}
	if randomFraction < 0 {
		randomFraction = 0
	}
	if randomFraction > 1 {
		randomFraction = 1
	}
	exponent := min(failureCount-1, 30)
	maximum := time.Duration(float64(InitialRetryDelay) * math.Pow(2, float64(exponent)))
	maximum = min(maximum, MaximumRetryDelay)
	delay := time.Duration(float64(maximum) * randomFraction)
	if serverRetryAfter > delay {
		delay = serverRetryAfter
	}
	return min(delay, MaximumRetryDelay)
}

func newBatchID() (string, error) {
	var value [16]byte
	if _, err := rand.Read(value[:]); err != nil {
		return "", fmt.Errorf("generate upload batch ID: %w", err)
	}
	value[6] = (value[6] & 0x0f) | 0x40
	value[8] = (value[8] & 0x3f) | 0x80
	encoded := hex.EncodeToString(value[:])
	return encoded[:8] + "-" + encoded[8:12] + "-" + encoded[12:16] + "-" +
		encoded[16:20] + "-" + encoded[20:], nil
}
