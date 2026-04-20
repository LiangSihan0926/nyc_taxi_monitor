"""Tests for taxi_monitor.ingest.  Network calls are stubbed via monkeypatch."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from taxi_monitor import ingest


def test_tlc_url_formats_month():
    url = ingest.tlc_url(2024, 1)
    assert url.endswith("yellow_tripdata_2024-01.parquet")
    assert url.startswith("https://")


def test_tlc_url_rejects_bad_month():
    with pytest.raises(ValueError):
        ingest.tlc_url(2024, 13)


def test_download_file_skips_existing(tmp_path: Path):
    dest = tmp_path / "already_here.bin"
    dest.write_bytes(b"hello")
    # No network call should happen — we assert by not patching requests.
    result = ingest.download_file("http://does.not.matter/x", dest)
    assert result == dest
    assert dest.read_bytes() == b"hello"


def test_download_file_streams(monkeypatch, tmp_path: Path):
    class FakeResp:
        def __init__(self, data: bytes):
            self._data = data

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def raise_for_status(self):
            return None

        def iter_content(self, chunk_size):
            for i in range(0, len(self._data), chunk_size):
                yield self._data[i : i + chunk_size]

    def fake_get(url, stream, timeout):  # noqa: ARG001
        return FakeResp(b"abcdef" * 3)

    import requests

    monkeypatch.setattr(requests, "get", fake_get)

    dest = tmp_path / "fresh" / "file.bin"
    out = ingest.download_file("http://x/y", dest, overwrite=True)
    assert out == dest
    assert dest.read_bytes() == b"abcdef" * 3


def test_load_trips_keeps_subset_of_columns(raw_trips_parquet: Path):
    df = ingest.load_trips(raw_trips_parquet)
    # Only YELLOW_COLUMNS that actually exist in the fixture should come back.
    assert set(df.columns).issubset(set(ingest.YELLOW_COLUMNS))
    assert len(df) > 0


def test_load_trips_missing_file(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        ingest.load_trips(tmp_path / "nope.parquet")


def test_load_zone_lookup(zone_lookup_csv: Path, zone_lookup_df: pd.DataFrame):
    out = ingest.load_zone_lookup(zone_lookup_csv)
    assert list(out.columns) == list(zone_lookup_df.columns)
    assert len(out) == len(zone_lookup_df)


def test_load_zone_lookup_rejects_bad_schema(tmp_path: Path):
    bad = tmp_path / "bad.csv"
    pd.DataFrame({"foo": [1]}).to_csv(bad, index=False)
    with pytest.raises(ValueError):
        ingest.load_zone_lookup(bad)


def test_load_zone_lookup_missing_file(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        ingest.load_zone_lookup(tmp_path / "missing.csv")


def test_download_wrappers_use_our_downloader(monkeypatch, tmp_path: Path):
    calls = []

    def fake_download(url, dest, overwrite=False, chunk_size=None):  # noqa: ARG001
        calls.append((url, Path(dest).name))
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(b"")
        return Path(dest)

    monkeypatch.setattr(ingest, "download_file", fake_download)
    trips = ingest.download_yellow_tripdata([(2024, 1), (2024, 2)], out_dir=tmp_path)
    assert len(trips) == 2
    zone = ingest.download_zone_lookup(out_dir=tmp_path)
    assert zone.name == "taxi_zone_lookup.csv"
    assert len(calls) == 3
