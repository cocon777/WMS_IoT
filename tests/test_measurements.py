import importlib.util
from pathlib import Path


def load_analyzer():
    spec = importlib.util.spec_from_file_location("analyzer", Path(__file__).parent / "measurements/analyze_export.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_loss_analysis_separates_boots_and_ignores_arrival_order():
    rows = [{"boot_id": boot, "seq": str(seq), "ts": "2026-11-01T00:00:00Z",
             "received_at": "2026-11-01T00:00:00.100Z"}
            for boot, seq in [("a", 3), ("a", 1), ("a", 3), ("b", 1)]]
    result = load_analyzer().analyze(rows)
    assert result["boots"]["a"]["missing_inside_observed_window"] == 1
    assert result["boots"]["a"]["duplicate_rows"] == 1
    assert result["boots"]["b"]["gap_percent"] == 0
    assert result["device_to_backend_ms"]["mean"] == 100


def test_empty_capture_does_not_claim_zero_latency():
    result = load_analyzer().analyze([])
    assert result["device_to_backend_ms"]["mean"] is None
