from synthia.metrics import llm_cost_usd_total, record_session_cost


def test_record_session_cost():
    initial_value = llm_cost_usd_total._value.get()

    record_session_cost(0.5)
    assert llm_cost_usd_total._value.get() == initial_value + 0.5

    record_session_cost(0.25)
    assert llm_cost_usd_total._value.get() == initial_value + 0.75


def test_record_session_cost_zero():
    initial_value = llm_cost_usd_total._value.get()
    record_session_cost(0.0)
    assert llm_cost_usd_total._value.get() == initial_value


def test_record_session_cost_negative():
    initial_value = llm_cost_usd_total._value.get()
    record_session_cost(-0.5)
    assert llm_cost_usd_total._value.get() == initial_value
