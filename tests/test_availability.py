from scaletest_mcp.availability import analyze_outages, evaluate_slo


def probe(start, end, success, sequence):
    return {
        "sequence": sequence,
        "started_at_utc": f"2026-01-01T00:00:{sequence:02d}Z",
        "ended_at_utc": f"2026-01-01T00:00:{sequence:02d}Z",
        "duration_ms": 20.0,
        "success": success,
        "_started": start,
        "_ended": end,
    }


def test_no_outage_passes_three_second_slo():
    probes = [probe(0.0, 0.02, True, 1), probe(0.25, 0.27, True, 2)]
    outages = analyze_outages(probes, [], 0.5)
    assert outages == []
    assert evaluate_slo(outages, 3000) == "PASS"


def test_outage_over_three_seconds_fails():
    probes = [
        probe(0.0, 0.02, True, 1),
        probe(0.5, 0.52, False, 2),
        probe(1.0, 1.02, False, 3),
        probe(4.0, 4.02, True, 4),
    ]
    outages = analyze_outages(probes, [], 4.5)
    assert len(outages) == 1
    assert outages[0]["estimated_downtime_ms"] > 3000
    assert evaluate_slo(outages, 3000) == "FAIL"


def test_sampling_uncertainty_returns_inconclusive():
    probes = [
        probe(0.0, 0.02, True, 1),
        probe(1.0, 1.02, False, 2),
        probe(3.5, 3.52, True, 3),
    ]
    outages = analyze_outages(probes, [], 4.0)
    assert outages[0]["estimated_downtime_ms"] <= 3000
    assert outages[0]["conservative_downtime_upper_bound_ms"] > 3000
    assert evaluate_slo(outages, 3000) == "INCONCLUSIVE"


def test_outage_is_linked_to_nearby_scaling_marker():
    probes = [
        probe(0.0, 0.02, True, 1),
        probe(1.0, 1.02, False, 2),
        probe(1.5, 1.52, True, 3),
    ]
    markers = [{
        "event_id": "event-1",
        "event_name": "scale_up",
        "timestamp_utc": "2026-01-01T00:00:01Z",
        "_mono": 1.1,
    }]
    outages = analyze_outages(probes, markers, 2.0)
    assert outages[0]["nearby_scaling_events"][0]["event_name"] == "scale_up"
