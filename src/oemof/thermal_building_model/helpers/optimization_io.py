from __future__ import annotations

import os
import pickle
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pandas as pd


def co2_factor_to_suffix(factor: float) -> str:
    value = float(factor)
    if value.is_integer():
        return str(int(value))
    suffix = f"{value:.6f}".rstrip("0").rstrip(".")
    if suffix.startswith("-0."):
        return "m0" + suffix[3:]
    if suffix.startswith("0."):
        return "0" + suffix[2:]
    return suffix.replace(".", "")


def atomic_pickle_dump(path: str | Path, payload: Any) -> None:
    path = str(path)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "wb") as fh:
        pickle.dump(payload, fh)


def load_pickle_dict_if_exists(path: str | Path) -> dict:
    path = str(path)
    if not os.path.exists(path):
        return {}
    with open(path, "rb") as fh:
        data = pickle.load(fh)
    return data if isinstance(data, dict) else {}


def safe_load_cluster_pickle(path: str | Path) -> pd.DataFrame:
    path = str(path)
    if not os.path.exists(path):
        return pd.DataFrame()
    with open(path, "rb") as fh:
        data = pickle.load(fh)
    if isinstance(data, pd.DataFrame):
        return data
    return pd.DataFrame(data)


def is_reference_k(k_value: Any) -> bool:
    return isinstance(k_value, str) and k_value.lower() == "reference"


def normalize_k_for_key(k_value: Any) -> Any:
    if isinstance(k_value, (tuple, list)):
        if len(k_value) != 2:
            raise ValueError(f"Expected k_value pair of length 2, got: {k_value}")
        return (
            normalize_k_for_key(k_value[0]),
            normalize_k_for_key(k_value[1]),
        )
    if is_reference_k(k_value):
        return "reference"
    return int(k_value)


def k_to_folder_token(k_value: Any) -> str:
    if is_reference_k(k_value):
        return "reference"
    return f"k{int(k_value):02d}"


def format_k_for_log(k_value: Any) -> str:
    if isinstance(k_value, (tuple, list)):
        if len(k_value) != 2:
            return str(k_value)
        return f"sfh={format_k_for_log(k_value[0])},mfh={format_k_for_log(k_value[1])}"
    return k_to_folder_token(k_value) if not is_reference_k(k_value) else "reference"


def dedupe_keep_order(items: list[Any]) -> list[Any]:
    out = []
    seen = set()
    for item in items:
        marker = item.lower() if isinstance(item, str) else item
        if marker in seen:
            continue
        seen.add(marker)
        out.append(item)
    return out


def parse_csv_tokens(raw_csv: Any) -> list[str]:
    if raw_csv is None:
        return []
    return [token.strip() for token in str(raw_csv).split(",") if token.strip()]


def parse_k_values(raw_csv: Any, *, dedupe: bool = False) -> list[Any]:
    values = []
    for token in parse_csv_tokens(raw_csv):
        if token.lower() == "reference":
            values.append("reference")
        else:
            values.append(int(token))
    return dedupe_keep_order(values) if dedupe else values


def parse_unique_k_values(raw_csv: Any) -> list[Any]:
    return parse_k_values(raw_csv, dedupe=True)


def parse_simple_ueu_cases(raw_csv: Any, *, dedupe: bool = False) -> list[str]:
    values = []
    for token in parse_csv_tokens(raw_csv):
        value = token.split(":", 1)[0].strip() if ":" in token else token.strip()
        if value:
            values.append(value)
    return dedupe_keep_order(values) if dedupe else values


def parse_unique_simple_ueu_cases(raw_csv: Any) -> list[str]:
    return parse_simple_ueu_cases(raw_csv, dedupe=True)


def parse_refurbishments(raw_csv: Any, *, dedupe: bool = False) -> list[str]:
    values = parse_csv_tokens(raw_csv)
    return dedupe_keep_order(values) if dedupe else values


def parse_unique_refurbishments(raw_csv: Any) -> list[str]:
    return parse_refurbishments(raw_csv, dedupe=True)


def script_base_path(file_path: str | Path) -> str:
    return os.path.dirname(os.path.abspath(str(file_path)))


def normalize_result_root(raw_value: Any, base_path: str | Path, *, label: str = "storage/check") -> str | None:
    if raw_value is None:
        return None

    value = str(raw_value).strip()
    if not value or value.lower() in {"none", "default"}:
        return None

    if len(value) >= 2 and value[1] == ":":
        normalized = value
    else:
        parsed = urlparse(value)
        if parsed.scheme and parsed.scheme != "file":
            if not parsed.path:
                raise ValueError(f"Invalid {label} URL without path: {value}")
            normalized = parsed.path
        elif parsed.scheme == "file":
            normalized = parsed.path
        else:
            normalized = value

    if not os.path.isabs(normalized):
        normalized = os.path.abspath(os.path.join(str(base_path), normalized))

    return os.path.normpath(normalized)
