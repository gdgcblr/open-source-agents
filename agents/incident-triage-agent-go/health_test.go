package main

import (
	"strings"
	"testing"
)

func TestVerdict(t *testing.T) {
	tests := []struct {
		name           string
		now, base, min float64
		dropIsBad      bool
		wantAbnormal   bool
		wantContains   string
	}{
		{"latency 25x", 2.485, 0.099, 0.05, false, true, "25.1x"},
		{"small wobble is normal", 0.11, 0.10, 0.05, false, false, "normal"},
		{"latency recovering is not an incident", 0.39, 2.43, 0.05, false, false, "improving"},
		{"traffic drop is an incident", 2, 20, 0.5, true, true, "dropped"},
		{"errors from zero", 0.08, 0, 0.01, false, true, "near zero"},
		{"tiny error ratios are ignored", 0.003, 0.001, 0.01, false, false, "normal"},
		{"memory 1.8x", 47.9, 26.1, 1, false, true, "1.8x"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := verdict(tt.now, tt.base, tt.min, tt.dropIsBad)
			if strings.HasPrefix(got, "ABNORMAL") != tt.wantAbnormal || !strings.Contains(got, tt.wantContains) {
				t.Errorf("verdict(%v, %v) = %q, want abnormal=%v containing %q", tt.now, tt.base, got, tt.wantAbnormal, tt.wantContains)
			}
		})
	}
}

func TestChangePoint(t *testing.T) {
	flat := []float64{1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1}
	if i := changePoint(flat); i != -1 {
		t.Errorf("flat series: got change at %d, want none", i)
	}
	step := []float64{1, 1, 1, 1, 1, 1, 1, 1, 9, 9, 9, 9}
	if i := changePoint(step); i != 8 {
		t.Errorf("step series: got change at %d, want 8", i)
	}
	spike := []float64{1, 1, 1, 1, 1, 9, 1, 1, 1, 1, 1, 1}
	if i := changePoint(spike); i != -1 {
		t.Errorf("single spike: got change at %d, want none (needs 3 points)", i)
	}
}

func TestLabelKeyIsStableAndDropsName(t *testing.T) {
	a := labelKey(map[string]string{"__name__": "up", "service": "checkout", "job": "shop"})
	b := labelKey(map[string]string{"job": "shop", "service": "checkout"})
	if a != b {
		t.Errorf("labelKey not stable: %q vs %q", a, b)
	}
}
