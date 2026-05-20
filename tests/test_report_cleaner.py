"""report_cleaner 单元测试."""
import os
from pathlib import Path

from core.report_cleaner import clean_reports


def _touch(p: Path, content: bytes = b"x") -> None:
    p.write_bytes(content)


def test_clean_reports_keeps_recent_groups(tmp_path: Path):
    rd = tmp_path / "reports"
    rd.mkdir()
    _touch(rd / "exporter.py")

    stem_old = "inspect_20200101_000000"
    stem_mid = "inspect_20200601_000000"
    stem_new = "inspect_20201201_000000"
    stamps = [(stem_old, 100), (stem_mid, 200), (stem_new, 300)]
    for stem, ts in stamps:
        for ext in ("json", "html"):
            p = rd / f"{stem}.{ext}"
            _touch(p)
            os.utime(p, (ts, ts))

    res = clean_reports(rd, keep=2, dry_run=False)
    assert sorted(p.name for p in res.deleted_paths) == [
        "inspect_20200101_000000.html",
        "inspect_20200101_000000.json",
    ]
    kept = sorted(p.name for p in res.kept_paths)
    assert kept == sorted(
        [
            "inspect_20200601_000000.html",
            "inspect_20200601_000000.json",
            "inspect_20201201_000000.html",
            "inspect_20201201_000000.json",
        ]
    )
    assert (rd / "exporter.py").exists()


def test_clean_reports_dry_run_no_unlink(tmp_path: Path):
    rd = tmp_path / "reports"
    rd.mkdir()
    stem_old = "api_smoke_20200101_000000"
    stem_new = "api_smoke_20201201_000000"
    po = rd / f"{stem_old}.json"
    pn = rd / f"{stem_new}.json"
    _touch(po)
    _touch(pn)
    os.utime(po, (100, 100))
    os.utime(pn, (300, 300))

    clean_reports(rd, keep=1, dry_run=True)
    assert (rd / f"{stem_old}.json").exists()
    assert (rd / f"{stem_new}.json").exists()
