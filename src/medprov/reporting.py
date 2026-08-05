"""Human-readable and machine-readable report rendering."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from .utils import assert_public_aggregate, write_json


def _markdown_value(value: Any, level: int = 0) -> list[str]:
    lines: list[str] = []
    if isinstance(value, dict):
        for key in sorted(value):
            child = value[key]
            if isinstance(child, (dict, list)):
                lines.append(f"{'  ' * level}- **{key}**")
                lines.extend(_markdown_value(child, level + 1))
            else:
                lines.append(f"{'  ' * level}- **{key}:** {child}")
    elif isinstance(value, list):
        for child in value:
            if isinstance(child, (dict, list)):
                lines.append(f"{'  ' * level}-")
                lines.extend(_markdown_value(child, level + 1))
            else:
                lines.append(f"{'  ' * level}- {child}")
    else:
        lines.append(f"{'  ' * level}{value}")
    return lines


def render_markdown(title: str, value: dict[str, Any]) -> str:
    return "# " + title + "\n\n" + "\n".join(_markdown_value(value)) + "\n"


def render_html(title: str, value: dict[str, Any]) -> str:
    payload = html.escape(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False))
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{html.escape(title)}</title>"
        "<style>body{font-family:Arial,sans-serif;max-width:1100px;margin:2rem auto;line-height:1.45}"
        "pre{white-space:pre-wrap;background:#f5f7fa;padding:1rem;border:1px solid #d8dee8}</style>"
        f"</head><body><h1>{html.escape(title)}</h1><pre>{payload}</pre></body></html>\n"
    )


def write_report_bundle(
    output_dir: str | Path, stem: str, title: str, value: dict[str, Any]
) -> dict[str, str]:
    assert_public_aggregate(value)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    json_path = write_json(destination / f"{stem}.json", value)
    md_path = destination / f"{stem}.md"
    html_path = destination / f"{stem}.html"
    md_path.write_text(render_markdown(title, value), encoding="utf-8")
    html_path.write_text(render_html(title, value), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path), "html": str(html_path)}
