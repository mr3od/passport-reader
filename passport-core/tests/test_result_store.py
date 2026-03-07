from __future__ import annotations

from passport_core.config import Settings
from passport_core.io import CsvResultStore, JsonResultStore, SqliteResultStore, build_result_store


def test_build_result_store_sqlite(tmp_path):
    settings = Settings(data_store_backend="sqlite", data_store_path=tmp_path)
    store = build_result_store(settings)
    assert isinstance(store, SqliteResultStore)


def test_build_result_store_json(tmp_path):
    settings = Settings(data_store_backend="json", data_store_path=tmp_path)
    store = build_result_store(settings)
    assert isinstance(store, JsonResultStore)


def test_build_result_store_csv(tmp_path):
    settings = Settings(data_store_backend="csv", data_store_path=tmp_path)
    store = build_result_store(settings)
    assert isinstance(store, CsvResultStore)
