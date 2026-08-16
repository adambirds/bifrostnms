package icmp

import (
	"errors"
	"math"
	"slices"
)

type Result struct {
	PacketsSent       int       `json:"packets_sent"`
	PacketsReceived   int       `json:"packets_received"`
	PacketLossPercent float64   `json:"packet_loss_percent"`
	MinimumRTTMS      *float64  `json:"min_rtt_ms"`
	AverageRTTMS      *float64  `json:"avg_rtt_ms"`
	MedianRTTMS       *float64  `json:"median_rtt_ms"`
	MaximumRTTMS      *float64  `json:"max_rtt_ms"`
	P95RTTMS          *float64  `json:"p95_rtt_ms"`
	JitterMS          *float64  `json:"jitter_ms"`
	RTTSamplesMS      []float64 `json:"rtt_samples_ms"`
}

func CalculateResult(packetsSent int, sequenceSamplesMS []float64) (Result, error) {
	if packetsSent < 1 || packetsSent > MaximumPacketCount || len(sequenceSamplesMS) > packetsSent {
		return Result{}, errors.New("ICMP packet counts are invalid")
	}
	for _, sample := range sequenceSamplesMS {
		if sample < 0 || math.IsNaN(sample) || math.IsInf(sample, 0) {
			return Result{}, errors.New("ICMP RTT samples must be finite and non-negative")
		}
	}
	result := Result{
		PacketsSent: packetsSent, PacketsReceived: len(sequenceSamplesMS),
		PacketLossPercent: 100 * float64(packetsSent-len(sequenceSamplesMS)) / float64(packetsSent),
		RTTSamplesMS:      slices.Clone(sequenceSamplesMS),
	}
	if len(sequenceSamplesMS) == 0 {
		return result, nil
	}
	sorted := slices.Clone(sequenceSamplesMS)
	slices.Sort(sorted)
	minimum, maximum := sorted[0], sorted[len(sorted)-1]
	var total float64
	for _, sample := range sorted {
		total += sample
	}
	average := total / float64(len(sorted))
	median, p95 := percentile(sorted, 0.5), percentile(sorted, 0.95)
	result.MinimumRTTMS, result.AverageRTTMS = &minimum, &average
	result.MedianRTTMS, result.MaximumRTTMS = &median, &maximum
	result.P95RTTMS = &p95
	if len(sequenceSamplesMS) > 1 {
		var differences float64
		for index := 1; index < len(sequenceSamplesMS); index++ {
			differences += math.Abs(sequenceSamplesMS[index] - sequenceSamplesMS[index-1])
		}
		jitter := differences / float64(len(sequenceSamplesMS)-1)
		result.JitterMS = &jitter
	}
	return result, nil
}

func percentile(sorted []float64, fraction float64) float64 {
	position := float64(len(sorted)-1) * fraction
	lower := int(math.Floor(position))
	upper := int(math.Ceil(position))
	if lower == upper {
		return sorted[lower]
	}
	weight := position - float64(lower)
	return sorted[lower] + (sorted[upper]-sorted[lower])*weight
}

func Assess(configuration Configuration, result Result) bool {
	if result.PacketsReceived == 0 {
		return false
	}
	if configuration.MaximumPacketLoss != nil &&
		result.PacketLossPercent > *configuration.MaximumPacketLoss {
		return false
	}
	if configuration.MaximumAverageRTTMS != nil && result.AverageRTTMS != nil &&
		*result.AverageRTTMS > *configuration.MaximumAverageRTTMS {
		return false
	}
	return true
}
