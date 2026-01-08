import json

from synthia.metrics import _calculate_llm_cost


def test_calculate_llm_cost(tmp_path, monkeypatch):
    stats_file = tmp_path / "stats-cache.json"
    stats_file.write_text(
        json.dumps(
            {
                "modelUsage": {
                    "claude-opus-4-5-20251101": {
                        "inputTokens": 278,
                        "outputTokens": 577,
                        "cacheReadInputTokens": 3710052,
                        "cacheCreationInputTokens": 247770,
                    }
                }
            }
        )
    )

    monkeypatch.setattr("synthia.metrics._STATS_CACHE_PATH", stats_file)

    expected_cost = (
        278 * 15.0 / 1_000_000 + 577 * 75.0 / 1_000_000 + 3710052 * 1.5 / 1_000_000 + 247770 * 18.75 / 1_000_000
    )
    assert abs(_calculate_llm_cost() - expected_cost) < 0.001


def test_calculate_llm_cost_missing_file(tmp_path, monkeypatch):
    stats_file = tmp_path / "nonexistent.json"
    monkeypatch.setattr("synthia.metrics._STATS_CACHE_PATH", stats_file)

    assert _calculate_llm_cost() == 0.0


def test_calculate_llm_cost_unknown_model(tmp_path, monkeypatch):
    stats_file = tmp_path / "stats-cache.json"
    stats_file.write_text(
        json.dumps(
            {
                "modelUsage": {
                    "unknown-model": {
                        "inputTokens": 1000,
                        "outputTokens": 500,
                    }
                }
            }
        )
    )

    monkeypatch.setattr("synthia.metrics._STATS_CACHE_PATH", stats_file)

    assert _calculate_llm_cost() == 0.0
