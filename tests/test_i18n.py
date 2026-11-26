"""Review page in Spanish, and spec-kit specs written in Spanish (#44)."""

import json
import re
import shutil
from pathlib import Path

from typer.testing import CliRunner

from unboringspec.adapters import get_adapter
from unboringspec.apply import apply_hint
from unboringspec.cli import app
from unboringspec.i18n import STRINGS, supported, table
from unboringspec.insights import apply_insights, heuristic_insights, parse_insights
from unboringspec.render import render_html

ROOT = Path(__file__).parent.parent
EN = ROOT / "examples/speckit/specs/001-photo-albums"
ES = ROOT / "examples/speckit-es/specs/001-albumes-compartidos"
runner = CliRunner()


# --- strings table ---------------------------------------------------------------


def test_both_languages_have_the_same_keys_and_placeholders():
    assert set(STRINGS["en"]) == set(STRINGS["es"])
    for key, text in STRINGS["en"].items():
        assert set(re.findall(r"\{(\w+)\}", text)) == set(re.findall(r"\{(\w+)\}", STRINGS["es"][key])), key


def test_no_key_shadows_a_dict_method():
    """In Jinja, t.copy would return dict.copy instead of the string."""
    assert not [k for k in STRINGS["en"] if k in dir(dict)]


def test_language_codes_fall_back_to_english():
    assert supported("es-ES") == "es" and supported("ES") == "es"
    assert supported("fr") == "en" and supported(None) == "en"
    assert table("fr")["h_judgment"] == "Needs your judgment"


# --- the page --------------------------------------------------------------------


def spanish_page():
    ir = get_adapter(ES).load(ES)
    insights = (ROOT / "schemas/examples/001-photo-albums.insights.json").read_text()
    ir, _ = apply_insights(ir, parse_insights(insights), "agent")
    return render_html(ir, lang="es")


def test_spanish_page_has_no_english_ui_left():
    html = spanish_page()
    assert '<html lang="es">' in html
    for spanish in ("1 · Necesita tu decisión", "2 · Decisiones que merece la pena mirar", "Vista visual",
                    "Alcance y plan", "✓ Aprobar", "Copiar para tu agente", "Exportar review.md"):
        assert spanish in html, spanish
    visible = re.sub(r"<script.*?</script>|<style.*?</style>", "", html, flags=re.S)
    for english in ("Needs your judgment", "Decisions worth a look", "Visual overview", "Scope and plan",
                    "✓ Approve", "Copy for your agent", "Export review.md</button>", "Transcript", "routine decisions"):
        assert english not in visible, english


def test_spanish_strings_reach_the_javascript_and_the_export():
    html = spanish_page()
    data = json.loads(html.split('<script id="data" type="application/json">')[1].split("</script>")[0].replace("<\\/", "</"))
    assert data["ui"]["js_answers_h"] == "Respuestas a las preguntas abiertas"
    assert data["ui"]["js_progress"] == "{done} de {total} puntos revisados"
    assert data["apply_hint"].startswith("Aplica esta revisión con los propios comandos de spec-kit")
    assert "fill(ui.js_review_title" in html and "ui.js_copied" in html


def test_english_stays_the_default():
    html = render_html(heuristic_insights(get_adapter(EN).load(EN)))
    assert '<html lang="en">' in html and "1 · Needs your judgment" in html


def test_apply_hint_in_both_languages():
    ad = get_adapter(EN)
    ir = ad.load(EN)
    assert apply_hint(ad, ir).startswith("Apply this review with spec-kit's own commands")
    assert apply_hint(ad, ir, "es").startswith("Aplica esta revisión")


def test_cli_render_lang(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    spec = tmp_path / "specs/001-albumes-compartidos"
    shutil.copytree(ES, spec)
    r = runner.invoke(app, ["review", str(spec), "--offline", "--lang", "es"])
    assert r.exit_code == 0, r.output
    assert "1 · Necesita tu decisión" in (tmp_path / ".unboring/001-albumes-compartidos/review.html").read_text()


# --- specs written in Spanish ------------------------------------------------------


def shape(ir):
    return dict(
        stories=[(s.id, s.priority) for s in ir.stories],
        requirements=[r.id for r in ir.requirements],
        tasks=[(t.id, t.story, t.parallel, t.done) for t in ir.tasks],
        phases=len({t.phase for t in ir.tasks}),
        decisions=[(d.id, len(d.alternatives), d.attention.value) for d in ir.decisions],
        questions=[q.sources[0].label for q in ir.questions],
        entities=[len(e.attributes) for e in ir.entities],
        warnings=ir.warnings,
    )


def test_spanish_speckit_spec_parses_like_the_english_one():
    en, es = get_adapter(EN).load(EN), get_adapter(ES).load(ES)
    assert shape(es) == shape(en)
    assert es.feature == "Álbumes de fotos compartidos"
    assert es.description.startswith("Que las familias creen álbumes")
    assert [s.title for s in es.stories][0] == "Crear un álbum y subir fotos"
    assert [d.title for d in es.decisions][:2] == ["Ruta de subida", "Modelo de invitación"]
    assert next(d for d in es.decisions if d.title == "Modelo de invitación").rationale.startswith("La menor fricción")


def test_spanish_task_graph_and_data_model():
    from unboringspec.diagrams import data_model, task_graph

    es = get_adapter(ES).load(ES)
    graph = task_graph(es).mermaid
    assert 'subgraph g0["1 · Preparación"]' in graph and 'subgraph g2["3 · HU1"]' in graph
    assert 'Álbum ||--o{ Foto : "has"' in data_model(es).mermaid


def test_spec_diagram_titles_and_generated_by_follow_the_language():
    html = render_html(heuristic_insights(get_adapter(ES).load(ES)), lang="es")
    assert "Grafo de tareas · 18 tareas en 6 fases" in html and "Modelo de datos · 3 entidades" in html
    assert "generado por análisis sin agente" in html
