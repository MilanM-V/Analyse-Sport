"""Audit du 2026-10-04, phase P3 : dette technique (architecture, code mort, CI, dashboard)."""
import importlib
import importlib.util
import json
import os
import re
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _py_files(*dirs):
    for d in dirs:
        for base, _, files in os.walk(os.path.join(ROOT, d)):
            for f in files:
                if f.endswith(".py"):
                    yield os.path.join(base, f)


def test_shared_layer_does_not_depend_on_nhl():
    offenders = [p for p in _py_files("shared")
                 if re.search(r"^\s*(from|import)\s+nhl\b", open(p, encoding="utf-8").read(), flags=re.M)]
    assert offenders == []


def test_no_silent_exception_in_production_code():
    pat = re.compile(r"except[^\n:]*:\s*(\n\s*)?pass\b")
    allowed = {os.path.join(ROOT, "nhl", "core", "database.py")}  # migrations : « colonne déjà présente »
    offenders = [p for p in _py_files(os.path.join("nhl", "core"), "shared", os.path.join("nhl", "data"))
                 if p not in allowed and pat.search(open(p, encoding="utf-8").read())]
    assert offenders == []


def test_dead_code_removed_from_production_modules():
    mf = importlib.import_module("nhl.core.market_filter")
    for name in ("load_ml_models", "prepare_features_for_player", "get_adaptive_ev_threshold"):
        assert not hasattr(mf, name)
    em = importlib.import_module("nhl.core.ensemble_model")
    assert not hasattr(em, "NHLEnsembleClassifier")
    bl = importlib.import_module("nhl.core.bot_logic")
    assert not hasattr(bl.NhlBot, "_calculate_quarter_kelly")
    for path in ("shared/kelly.py", "nhl/core/kelly.py", "nhl/scripts/train_production_models.py"):
        assert not os.path.exists(os.path.join(ROOT, path))


def test_legacy_code_still_replays_historical_phases():
    from nhl.sim.legacy import CATEGORY_CAPS, NHLEnsembleClassifier, calculate_quarter_kelly, is_cote_valid
    from nhl.sim.phases import PHASES
    # Kelly 1/8 historique : f = (0,30 × 3 − 0,70) / 3 = 0,0667 → 0,83 U → arrondi 1,0 U
    assert calculate_quarter_kelly(0.30, 4.0, "BUTEUR") == "1.0 U"
    assert calculate_quarter_kelly(0.21, 5.0, "BUTEUR") == "0.5 U"  # plancher 0,5 U de l'ancien code
    assert CATEGORY_CAPS["PASSEUR"] == 2.0
    assert is_cote_valid({"Joueur": "X", "Cote": 5.0, "Proba": 0.30}, 4.5)
    assert PHASES["baseline"]().model_factory("but").__class__ is NHLEnsembleClassifier


def test_ci_workflow_is_versioned_with_python_312():
    wf = os.path.join(ROOT, ".github", "workflows", "tests.yml")
    text = open(wf, encoding="utf-8").read()
    assert '"3.12"' in text and "test" in text
    ignored = subprocess.run(["git", "check-ignore", "-q", wf], cwd=ROOT).returncode == 0
    assert not ignored


def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout


def test_dashboard_published_to_dedicated_branch(tmp_path, monkeypatch):
    # Chargé par chemin : `dashboard` désigne aussi nhl/dashboard.py (Streamlit) dans le sys.path des tests
    spec = importlib.util.spec_from_file_location("dashboard_exporter", os.path.join(ROOT, "dashboard", "exporter.py"))
    ex = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ex)
    remote = tmp_path / "remote.git"
    _git(["init", "-q", "--bare", str(remote)], str(tmp_path))
    data = tmp_path / "data.json"
    data.write_text(json.dumps({"balance": 101.5}), encoding="utf-8")
    monkeypatch.setattr(ex, "OUTPUT_JSON", str(data))
    clone = tmp_path / "pub"
    assert ex.git_commit_and_push(repo_dir=str(clone), remote_url=str(remote)) is True
    assert json.loads(_git(["show", "dashboard-data:data.json"], str(remote))) == {"balance": 101.5}
    assert ex.git_commit_and_push(repo_dir=str(clone), remote_url=str(remote)) is False  # inchangé
    data.write_text(json.dumps({"balance": 99.0}), encoding="utf-8")
    assert ex.git_commit_and_push(repo_dir=str(clone), remote_url=str(remote)) is True
    assert json.loads(_git(["show", "dashboard-data:data.json"], str(remote))) == {"balance": 99.0}
    assert _git(["branch", "--list"], str(remote)).split() == ["dashboard-data"]  # aucune autre branche touchée
