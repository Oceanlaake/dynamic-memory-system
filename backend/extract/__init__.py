"""LoCoMo -> Structured Memory extraction (task A2).

The public entry points are:

- :func:`backend.extract.pipeline.extract_dataset` – build Memory JSON for many samples.
- :func:`backend.extract.pipeline.extract_sample` – build Memory JSON for one sample.
- :func:`backend.extract.locomo.load_dataset` – parse the raw LoCoMo file.
- :func:`backend.extract.postprocess.validate_document` – check output against
  ``APIs/memory_schema.json``.
"""

from __future__ import annotations

from backend.extract.locomo import Sample, Session, Turn, load_dataset, normalize_sample
from backend.extract.pipeline import extract_dataset, extract_sample
from backend.extract.postprocess import validate_document

__all__ = [
    "Sample",
    "Session",
    "Turn",
    "extract_dataset",
    "extract_sample",
    "load_dataset",
    "normalize_sample",
    "validate_document",
]
