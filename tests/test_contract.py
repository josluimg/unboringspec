"""The insights contract is public: agents of any kind must return JSON that matches
schemas/insights.v<N>.schema.json. These tests keep the published file, the Pydantic
model and the example in sync."""

import json
from pathlib import Path

import jsonschema
from typer.testing import CliRunner

from unboringspec.adapters import get_adapter
from unboringspec.cli import app
from unboringspec.insights import SCHEMA_ID, SCHEMA_VERSION, apply_insights, json_schema, parse_insights

ROOT = Path(__file__).parent.parent
PUBLISHED = ROOT / f"schemas/insights.v{SCHEMA_VERSION}.schema.json"
EXAMPLE_INSIGHTS = ROOT / "schemas/examples/001-photo-albums.insights.json"
EXAMPLE_SPEC = ROOT / "examples/speckit/specs/001-photo-albums"


def test_published_schema_matches_model():
    published = json.loads(PUBLISHED.read_text())
    assert published == json_schema(), (
        f"{PUBLISHED.name} is out of date. Regenerate it with: unboring schema > {PUBLISHED.relative_to(ROOT)}"
    )
    assert published["$id"] == SCHEMA_ID
    assert SCHEMA_ID.endswith(PUBLISHED.relative_to(ROOT).as_posix())


def test_published_schema_is_valid_json_schema():
    jsonschema.Draft202012Validator.check_schema(json.loads(PUBLISHED.read_text()))


def test_example_validates_against_published_schema():
    schema = json.loads(PUBLISHED.read_text())
    example = json.loads(EXAMPLE_INSIGHTS.read_text())
    jsonschema.validate(example, schema)


def test_example_citations_all_resolve():
    ir = get_adapter(EXAMPLE_SPEC).load(EXAMPLE_SPEC)
    _, dropped = apply_insights(ir, parse_insights(EXAMPLE_INSIGHTS.read_text()), "test")
    assert dropped == 0


def test_schema_rejects_uncited_items():
    schema = json.loads(PUBLISHED.read_text())
    example = json.loads(EXAMPLE_INSIGHTS.read_text())
    example["decisions"][0]["sources"] = []
    try:
        jsonschema.validate(example, schema)
    except jsonschema.ValidationError:
        return
    raise AssertionError("the published schema must require at least one citation")


def test_parsing_is_lenient_where_the_schema_is_strict():
    """One uncited item is dropped with a count, not a failed review."""
    example = json.loads(EXAMPLE_INSIGHTS.read_text())
    example["decisions"][0]["sources"] = []
    ir = get_adapter(EXAMPLE_SPEC).load(EXAMPLE_SPEC)
    _, dropped = apply_insights(ir, parse_insights(json.dumps(example)), "test")
    assert dropped == 1


def test_schema_command_prints_published_schema():
    r = CliRunner().invoke(app, ["schema"])
    assert r.exit_code == 0
    assert json.loads(r.output) == json.loads(PUBLISHED.read_text())
