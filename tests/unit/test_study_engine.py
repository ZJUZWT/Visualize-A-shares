import importlib


def test_study_engine_uses_global_db_path(monkeypatch):
    study_module = importlib.import_module("engine.study.engine")
    from config import DB_PATH

    captured: dict[str, object] = {}

    class _DummyConn:
        pass

    def _fake_connect(path: str):
        captured["path"] = path
        return _DummyConn()

    def _fake_ensure_tables(conn):
        captured["conn"] = conn

    monkeypatch.setattr(study_module.duckdb, "connect", _fake_connect)
    monkeypatch.setattr(study_module, "_ensure_tables", _fake_ensure_tables)

    engine = study_module.StudyEngine()

    assert captured["path"] == str(DB_PATH)
    assert isinstance(captured["conn"], _DummyConn)
    assert isinstance(engine, study_module.StudyEngine)


def test_study_engine_knowledge_graph_path_uses_data_dir():
    study_module = importlib.import_module("engine.study.engine")
    from config import DATA_DIR

    assert study_module._get_knowledge_graph_path() == DATA_DIR / "expert_kg.json"
