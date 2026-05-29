from synthia.metrics import (
    llm_call_cost_usd,
    llm_cost_usd_total,
    llm_session_cost_usd,
    record_call_cost,
    record_session_cost,
)


def test_record_call_cost_increments_cumulative_total():
    model = "test-call-model"
    initial = llm_cost_usd_total.labels(model=model)._value.get()

    record_call_cost(model, 0.5)
    assert llm_cost_usd_total.labels(model=model)._value.get() == initial + 0.5

    record_call_cost(model, 0.25)
    assert llm_cost_usd_total.labels(model=model)._value.get() == initial + 0.75


def test_record_call_cost_observes_call_histogram():
    model = "test-call-hist-model"
    initial_sum = llm_call_cost_usd.labels(model=model)._sum.get()
    record_call_cost(model, 0.3)
    assert llm_call_cost_usd.labels(model=model)._sum.get() == initial_sum + 0.3


def test_record_session_cost_observes_session_histogram_only():
    model = "test-session-model"
    initial_sum = llm_session_cost_usd.labels(model=model)._sum.get()
    initial_total = llm_cost_usd_total.labels(model=model)._value.get()

    record_session_cost(model, 0.4)
    assert llm_session_cost_usd.labels(model=model)._sum.get() == initial_sum + 0.4
    assert llm_cost_usd_total.labels(model=model)._value.get() == initial_total


def test_cost_ignores_zero_and_negative():
    model = "test-ignore-model"
    initial_total = llm_cost_usd_total.labels(model=model)._value.get()
    initial_call_sum = llm_call_cost_usd.labels(model=model)._sum.get()
    initial_session_sum = llm_session_cost_usd.labels(model=model)._sum.get()

    record_call_cost(model, 0.0)
    record_call_cost(model, -0.5)
    record_session_cost(model, 0.0)
    record_session_cost(model, -0.5)

    assert llm_cost_usd_total.labels(model=model)._value.get() == initial_total
    assert llm_call_cost_usd.labels(model=model)._sum.get() == initial_call_sum
    assert llm_session_cost_usd.labels(model=model)._sum.get() == initial_session_sum
