package main

import "testing"

func TestCardHistoryRecordsProgressWithoutWaitingForSampleInterval(t *testing.T) {
	previous := factoryCardSnapshot{Ts: 1000, Auto: 12400, Imported: 30102}
	current := previous
	current.Ts++
	if shouldRecordCardSnapshot(previous, current) {
		t.Fatal("unchanged browser refresh must not append a duplicate sample")
	}
	current.Auto++
	if !shouldRecordCardSnapshot(previous, current) {
		t.Fatal("new enabled cards must update the unattended progress clock immediately")
	}
	current = previous
	current.Ts += 900
	if !shouldRecordCardSnapshot(previous, current) {
		t.Fatal("unchanged output must still receive periodic measurements")
	}
}
