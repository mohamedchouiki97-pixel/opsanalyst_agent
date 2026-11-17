"""Load and validate the active dataset's YAML files (dictionary + glossary).

Everything dataset-specific lives in datasets/<name>/. The agent code only ever
reads it through these functions, so switching datasets is one setting (DATASET=...).

extra="forbid" everywhere: a typo in a YAML key (e.g. "synonym:") fails loudly at
load time instead of being silently ignored.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from agent.config import get_settings

DATASETS_ROOT = Path("datasets")


# --- dictionary.yaml -----------------------------------------------------------


class TableInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str
    notes: list[str] = []
    pii_columns: list[str] = []
    columns: dict[str, str]  # column name -> description


class Dictionary(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_name: str = Field(alias="schema")
    tables: dict[str, TableInfo]


# --- glossary.yaml -------------------------------------------------------------


class GlossaryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    term: str
    synonyms: list[str] = []
    definition: str
    sql: str | None = None
    filters: list[str] = []
    tables: list[str] = []
    notes: str | None = None


class Glossary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entries: list[GlossaryEntry]

    @field_validator("entries")
    @classmethod
    def terms_are_unique(cls, entries: list[GlossaryEntry]) -> list[GlossaryEntry]:
        seen = set()
        for entry in entries:
            key = entry.term.lower()
            if key in seen:
                raise ValueError(f"duplicate glossary term: {entry.term}")
            seen.add(key)
        return entries


# --- Loaders -------------------------------------------------------------------


def dataset_dir(dataset: str | None = None) -> Path:
    path = DATASETS_ROOT / (dataset or get_settings().dataset)
    if not path.is_dir():
        raise FileNotFoundError(f"dataset folder not found: {path}")
    return path


def _read_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_dictionary(dataset: str | None = None) -> Dictionary:
    return Dictionary.model_validate(_read_yaml(dataset_dir(dataset) / "dictionary.yaml"))


def load_glossary(dataset: str | None = None) -> Glossary:
    return Glossary.model_validate(_read_yaml(dataset_dir(dataset) / "glossary.yaml"))
