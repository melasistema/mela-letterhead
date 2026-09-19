"""Lengths, colours and page sizes as written in ``letterhead.yaml``.

JSON has no length type, so everything that reaches Typst is a plain number in
typographic points and the Typst side multiplies it by ``1pt``. Converting here
rather than there keeps the Typst module free of parsing logic.

Two families of measurement are accepted, and each field belongs to exactly one:

``absolute``
    A physical length: ``22mm``, ``1in``, ``11.5pt``. Converted to points.

``relative``
    A multiple of the current font size: ``0.82em``, or the bare number
    ``0.82``. Kept as a float, multiplied by ``1em`` in Typst. Used for
    leading and paragraph spacing, which must scale with whatever text they
    are applied to.

``ratio``
    A share of the space available: ``60%``, or the bare number ``0.6``. Kept
    as a fraction, multiplied by ``100%`` in Typst. Used for the width of an
    image, which is measured against the column it sits in rather than
    against the paper.
"""

from __future__ import annotations

import re
from typing import Dict, Tuple, Union

from .errors import ConfigError

Number = Union[int, float]

#: Points per unit. Typst's point is the PostScript point: 72 to the inch.
_POINTS_PER_UNIT: Dict[str, float] = {
    "pt": 1.0,
    "mm": 72.0 / 25.4,
    "cm": 72.0 / 2.54,
    "in": 72.0,
    "pc": 12.0,
}

_ABSOLUTE_RE = re.compile(
    r"^\s*([+-]?(?:\d+(?:\.\d+)?|\.\d+))\s*(pt|mm|cm|in|pc)?\s*$",
    re.IGNORECASE,
)
_RELATIVE_RE = re.compile(
    r"^\s*([+-]?(?:\d+(?:\.\d+)?|\.\d+))\s*(em)?\s*$",
    re.IGNORECASE,
)
_RATIO_RE = re.compile(r"^\s*([+-]?(?:\d+(?:\.\d+)?|\.\d+))\s*(%)?\s*$")

#: A share this far above the whole is a mistyped percentage, not a design.
_RATIO_CEILING = 5.0

_HEX_COLOUR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")

#: Named page sizes, in millimetres, portrait.
_PAGE_SIZES_MM: Dict[str, Tuple[float, float]] = {
    "a3": (297.0, 420.0),
    "a4": (210.0, 297.0),
    "a5": (148.0, 210.0),
    "b5": (176.0, 250.0),
    "letter": (215.9, 279.4),
    "legal": (215.9, 355.6),
    "executive": (184.15, 266.7),
}


def to_points(value: Union[str, Number], field: str) -> float:
    """Return ``value`` in points.

    A bare number is read as points, so ``11`` and ``"11pt"`` agree.
    """
    if isinstance(value, bool):  # bool is an int; reject it before the number path
        raise ConfigError(f"{field}: expected a length, got a boolean")
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        raise ConfigError(f"{field}: expected a length such as '22mm', got {value!r}")

    match = _ABSOLUTE_RE.match(value)
    if match is None:
        raise ConfigError(
            f"{field}: {value!r} is not a length",
            hint="Use a number followed by pt, mm, cm, in or pc — for example '22mm'.",
        )
    amount, unit = match.group(1), (match.group(2) or "pt").lower()
    return float(amount) * _POINTS_PER_UNIT[unit]


def to_em(value: Union[str, Number], field: str) -> float:
    """Return ``value`` as a multiple of the font size.

    ``0.82`` and ``"0.82em"`` are the same thing. Absolute units are rejected
    here on purpose: a leading fixed in points stops tracking the text it sets.
    """
    if isinstance(value, bool):
        raise ConfigError(f"{field}: expected a multiple of the font size, got a boolean")
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        raise ConfigError(f"{field}: expected a value such as '0.82em', got {value!r}")

    match = _RELATIVE_RE.match(value)
    if match is None:
        raise ConfigError(
            f"{field}: {value!r} is not a multiple of the font size",
            hint="Use a plain number or one followed by 'em' — for example '0.82em'. "
            "Absolute units are not accepted here, because this value has to "
            "scale with the text it applies to.",
        )
    return float(match.group(1))


def to_ratio(value: Union[str, Number], field: str) -> float:
    """Return ``value`` as a fraction of the space available.

    ``"60%"`` and ``0.6`` are the same thing. A bare number is a fraction and
    never a percentage, so ``60`` is sixty times the column — refused here,
    where the setting can still be named, rather than printed as an image
    running off the page.
    """
    if isinstance(value, bool):
        raise ConfigError(f"{field}: expected a share such as '60%', got a boolean")
    if isinstance(value, (int, float)):
        ratio = float(value)
    elif isinstance(value, str):
        match = _RATIO_RE.match(value)
        if match is None:
            raise ConfigError(
                f"{field}: {value!r} is not a share of the width",
                hint="Use a percentage such as '60%', or the fraction 0.6.",
            )
        ratio = float(match.group(1))
        if match.group(2):
            ratio /= 100.0
    else:
        raise ConfigError(f"{field}: expected a share such as '60%', got {value!r}")

    if ratio <= 0 or ratio > _RATIO_CEILING:
        raise ConfigError(
            f"{field}: {value!r} is not a usable share of the width",
            hint="Use a percentage such as '60%', or the fraction 0.6. A bare "
            "number is read as a fraction, so '60' would be sixty times the "
            "width of the column.",
        )
    return ratio


def to_colour(value: object, field: str) -> str:
    """Validate a ``#rgb`` / ``#rrggbb`` / ``#rrggbbaa`` colour and return it."""
    if not isinstance(value, str) or not _HEX_COLOUR_RE.match(value):
        raise ConfigError(
            f"{field}: {value!r} is not a colour",
            hint="Use a hexadecimal colour such as '#f5f5f7', '#fff' or '#00000080'.",
        )
    return value


def page_size(value: object, field: str) -> Tuple[float, float]:
    """Return ``(width, height)`` in points for a named or explicit page size.

    Accepts a name (``a4``, ``letter``, optionally suffixed ``-landscape``) or a
    mapping with ``width`` and ``height``.
    """
    if isinstance(value, dict):
        missing = [key for key in ("width", "height") if key not in value]
        if missing:
            raise ConfigError(
                f"{field}: a custom page size needs both 'width' and 'height' "
                f"(missing: {', '.join(missing)})"
            )
        return (
            to_points(value["width"], f"{field}.width"),
            to_points(value["height"], f"{field}.height"),
        )

    if not isinstance(value, str):
        raise ConfigError(f"{field}: expected a page size name or a width/height pair")

    name = value.strip().lower()
    landscape = False
    for suffix in ("-landscape", "_landscape", " landscape"):
        if name.endswith(suffix):
            name, landscape = name[: -len(suffix)], True
            break

    if name not in _PAGE_SIZES_MM:
        known = ", ".join(sorted(_PAGE_SIZES_MM))
        raise ConfigError(
            f"{field}: unknown page size {value!r}",
            hint=f"Known sizes: {known}. Append '-landscape' to rotate one, or give "
            "an explicit 'width' and 'height' instead.",
        )

    width_mm, height_mm = _PAGE_SIZES_MM[name]
    if landscape:
        width_mm, height_mm = height_mm, width_mm
    per_mm = _POINTS_PER_UNIT["mm"]
    return width_mm * per_mm, height_mm * per_mm
