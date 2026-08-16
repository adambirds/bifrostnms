package icmp

import (
	"math"
	"testing"
)

func TestCalculateResultPreservesSequenceAndSpecifiedStatistics(t *testing.T) {
	samples := []float64{30, 10, 20, 40}
	result, err := CalculateResult(5, samples)
	if err != nil {
		t.Fatalf("calculate result: %v", err)
	}
	assertNear(t, result.PacketLossPercent, 20)
	assertNear(t, *result.MinimumRTTMS, 10)
	assertNear(t, *result.AverageRTTMS, 25)
	assertNear(t, *result.MedianRTTMS, 25)
	assertNear(t, *result.MaximumRTTMS, 40)
	assertNear(t, *result.P95RTTMS, 38.5)
	assertNear(t, *result.JitterMS, 50.0/3.0)
	for index, sample := range samples {
		assertNear(t, result.RTTSamplesMS[index], sample)
	}
}

func TestCalculateResultUsesNullLatencyForNoReplies(t *testing.T) {
	result, err := CalculateResult(3, nil)
	if err != nil {
		t.Fatalf("calculate complete loss: %v", err)
	}
	if result.PacketLossPercent != 100 || result.MinimumRTTMS != nil ||
		result.AverageRTTMS != nil || result.JitterMS != nil || Assess(DefaultConfiguration(), result) {
		t.Fatalf("complete-loss result = %#v", result)
	}
}

func TestAssessmentAppliesPacketLossAndLatencyThresholds(t *testing.T) {
	maximumLoss, maximumAverage := 10.0, 15.0
	configuration := DefaultConfiguration()
	configuration.MaximumPacketLoss = &maximumLoss
	configuration.MaximumAverageRTTMS = &maximumAverage
	healthy, _ := CalculateResult(2, []float64{10, 12})
	if !Assess(configuration, healthy) {
		t.Fatal("healthy samples were assessed as unhealthy")
	}
	highLoss, _ := CalculateResult(2, []float64{10})
	if Assess(configuration, highLoss) {
		t.Fatal("excessive packet loss was assessed as healthy")
	}
	highLatency, _ := CalculateResult(2, []float64{20, 30})
	if Assess(configuration, highLatency) {
		t.Fatal("excessive latency was assessed as healthy")
	}
}

func assertNear(t *testing.T, actual float64, expected float64) {
	t.Helper()
	if math.Abs(actual-expected) > 1e-9 {
		t.Fatalf("value = %v, want %v", actual, expected)
	}
}
