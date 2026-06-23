import pytest

from synthia.agents.personas import (
    PERSONAS,
    get_persona,
    persona_directive,
    persona_system_prompt,
)

_HAT_IDS = {"white", "red", "black", "yellow", "green", "blue"}


@pytest.mark.smoke
def test_personas_cover_the_six_hats_with_unique_ids() -> None:
    ids = [p.id for p in PERSONAS]

    assert set(ids) == _HAT_IDS
    assert len(ids) == len(set(ids))
    assert all(p.label and p.emoji and p.fragment and p.stance for p in PERSONAS)


@pytest.mark.smoke
@pytest.mark.parametrize("persona_id", sorted(_HAT_IDS))
def test_directive_and_system_prompt_present_for_each_hat(persona_id: str) -> None:
    persona = get_persona(persona_id)
    directive = persona_directive(persona_id)
    system = persona_system_prompt(persona_id)

    assert persona is not None
    assert directive is not None
    assert persona.label in directive
    assert "delegate" in directive
    assert system is not None
    assert persona.label in system


@pytest.mark.smoke
@pytest.mark.parametrize("persona_id", [None, "", "default", "purple", "unknown"])
def test_unknown_or_default_yields_nothing(persona_id: str | None) -> None:
    assert get_persona(persona_id) is None
    assert persona_directive(persona_id) is None
    assert persona_system_prompt(persona_id) is None
