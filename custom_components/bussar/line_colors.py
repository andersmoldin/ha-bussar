"""Färg per linjenummer, sparad i postens options."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from homeassistant.config_entries import ConfigEntry

from .const import OPTION_LINE_COLORS


def line_color(entry: ConfigEntry, line: str) -> str | None:
    """Linjens färg som #rrggbb, eller None när ingen färg är vald."""
    colors: dict[str, str] = entry.options.get(OPTION_LINE_COLORS, {})
    return colors.get(line)


def with_line_color(options: dict[str, Any], line: str, rgb: Sequence[int]) -> dict[str, Any]:
    """Postens options med linjens färg satt."""
    r, g, b = rgb
    colors = {**options.get(OPTION_LINE_COLORS, {}), line: f"#{r:02x}{g:02x}{b:02x}"}
    return {**options, OPTION_LINE_COLORS: colors}


def without_line_color(options: dict[str, Any], line: str) -> dict[str, Any]:
    """Postens options utan färg för linjen, så att temats färger gäller."""
    colors = {k: v for k, v in options.get(OPTION_LINE_COLORS, {}).items() if k != line}
    return {**options, OPTION_LINE_COLORS: colors}


def as_rgb(color: str) -> list[int]:
    """#rrggbb som [r, g, b], för HA:s färgväljare."""
    return [int(color[i : i + 2], 16) for i in (1, 3, 5)]
