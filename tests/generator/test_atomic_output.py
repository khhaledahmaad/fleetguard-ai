from pathlib import Path

import pytest
from pydantic import BaseModel

from fleetguard.generator.output import _atomic_text, _write_jsonl


def test_failed_publication_preserves_previous_complete_file(tmp_path, monkeypatch):
    from fleetguard.generator import output

    target = tmp_path / "complete.txt"
    target.write_text("previous", encoding="utf-8")

    def fail(*args):
        raise OSError("publication unavailable")

    monkeypatch.setattr(output.os, "replace", fail)
    with pytest.raises(OSError, match="publication unavailable"):
        _atomic_text(target, "new")
    assert target.read_text(encoding="utf-8") == "previous"
    assert list(tmp_path.iterdir()) == [target]


def test_large_jsonl_is_complete_after_publication(tmp_path):
    class Record(BaseModel):
        sequence: int
        content: str

    target = Path(tmp_path) / "records.jsonl"
    count = _write_jsonl(target, (Record(sequence=i, content="track" * 200) for i in range(6000)))
    with target.open(encoding="utf-8") as stream:
        records = [Record.model_validate_json(line) for line in stream]
    assert count == len(records) == 6000
    assert [record.sequence for record in records] == list(range(6000))
