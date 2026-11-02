import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.schemas.generative_ui import ViewEnvelope


FIXTURE = (Path(__file__).resolve().parents[2] / "fixtures" / "generative-ui" / "v1.json")


def fixture_payload():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_shared_v1_fixture_is_a_valid_trusted_view_envelope():
    envelope = ViewEnvelope.model_validate(fixture_payload())

    assert envelope.schema_version == 1
    assert envelope.spec.root == "root"
    assert envelope.trusted_data.metrics["fixture-bill:consumption_fen"].value == 10000


def test_generative_ui_setting_defaults_on_and_reads_environment(monkeypatch):
    monkeypatch.delenv("GENERATIVE_UI_ENABLED", raising=False)
    assert Settings(_env_file=None).generative_ui_enabled is True

    monkeypatch.setenv("GENERATIVE_UI_ENABLED", "false")
    assert Settings(_env_file=None).generative_ui_enabled is False


@pytest.mark.parametrize(
    "mutate",
    [
        lambda data: data["spec"]["elements"]["total"]["props"].update(metric_ref="missing"),
        lambda data: data["spec"]["elements"]["total"]["props"].update(color="red"),
        lambda data: data["spec"]["elements"]["categories"].update(
            props={"dataset_ref": "fixture-bill:consumption_fen"}
        ),
        lambda data: data["spec"]["elements"]["categories"]["props"].update(
            dataset_ref={"untrusted": "object"}
        ),
        lambda data: data["spec"]["elements"].update({
            "wrapper": {"type": "Stack", "props": {}, "children": ["total"]},
        }) or data["spec"]["elements"]["root"].update(
            children=["total", "categories", "wrapper"]
        ),
        lambda data: data["spec"]["elements"]["root"]["children"].append("total"),
    ],
)
def test_view_schema_rejects_untrusted_or_semantically_wrong_component_props(mutate):
    data = fixture_payload()
    mutate(data)

    with pytest.raises(ValidationError):
        ViewEnvelope.model_validate(data)
