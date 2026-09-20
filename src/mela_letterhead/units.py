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
    against the paper. :func:`to_alpha` is the same family bounded to
    nought…one, for a share that is an opacity rather than a width.

``share``
    A ratio that also accepts an absolute length and divides it by a known
    whole. Used for the parts of the wordmark, which are proportions of the
    space the mark occupies — so that the smaller mark in the running header
    is the same design, not a different one — but which a user would rather
    write as ``32pt``.
"""

from __future__ import annotations

import re

from .errors import ConfigError

# Evaluated when the module is imported rather than deferred like an
# annotation, so this one needs PEP 604 at runtime — which the 3.10 floor is.
Number = int | float

#: Points per unit. Typst's point is the PostScript point: 72 to the inch.
_POINTS_PER_UNIT: dict[str, float] = {
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

_SHARE_HINT = "Use a fraction such as 0.002, a percentage, or a length such as '0.4pt'."

_ALPHA_HINT = (
    "Use a percentage such as '35%', or the fraction 0.35. Nought is none of it "
    "and 1 is all of it."
)

_HEX_COLOUR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")

#: Named page sizes, in millimetres, portrait.
_PAGE_SIZES_MM: dict[str, tuple[float, float]] = {
    "a3": (297.0, 420.0),
    "a4": (210.0, 297.0),
    "a5": (148.0, 210.0),
    "b5": (176.0, 250.0),
    "letter": (215.9, 279.4),
    "legal": (215.9, 355.6),
    "executive": (184.15, 266.7),
}


def to_points(value: str | Number, field: str, positive: bool = True) -> float:
    """Return ``value`` in points.

    A bare number is read as points, so ``11`` and ``"11pt"`` agree.

    ``positive`` is false for the few lengths a negative one says something
    about — tracking, an offset that pushes a band off the edge of the paper,
    the nudge under a mark. Everywhere else a negative is a typing mistake:
    a height of ``-5mm`` is not a short band, it is a page Typst lays out in
    some way nobody intended, and saying so here names the setting.
    """
    if isinstance(value, bool):  # bool is an int; reject it before the number path
        raise ConfigError(f"{field}: expected a length, got a boolean")
    if isinstance(value, (int, float)):
        return _signed(float(value), value, field, positive)
    if not isinstance(value, str):
        raise ConfigError(f"{field}: expected a length such as '22mm', got {value!r}")

    match = _ABSOLUTE_RE.match(value)
    if match is None:
        raise ConfigError(
            f"{field}: {value!r} is not a length",
            hint="Use a number followed by pt, mm, cm, in or pc — for example '22mm'.",
        )
    amount, unit = match.group(1), (match.group(2) or "pt").lower()
    return _signed(float(amount) * _POINTS_PER_UNIT[unit], value, field, positive)


def _signed(points: float, written: object, field: str, positive: bool) -> float:
    """Refuse a negative length where a negative length means nothing."""
    if positive and points < 0:
        raise ConfigError(
            f"{field}: {written!r} is not a length this setting can take",
            hint="This one cannot be negative. Use nought to turn it off.",
        )
    return points


def to_em(value: str | Number, field: str) -> float:
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


def to_ratio(value: str | Number, field: str) -> float:
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


def to_share(
    value: str | Number, field: str, whole: float, positive: bool = True
) -> float:
    """Return ``value`` as a fraction of ``whole``.

    A share is written as ``0.17`` or ``'17%'``, exactly as :func:`to_ratio`
    takes it. A length — ``'32pt'``, ``'11mm'`` — is divided by ``whole``
    instead, so that a user may write the size they want and still get a
    proportion, which is what keeps a mark recognisable at two sizes.

    ``positive`` is false for values that may legitimately be zero or negative,
    such as tracking.
    """
    if isinstance(value, str):
        match = _ABSOLUTE_RE.match(value)
        # Only with a unit: a bare "0.17" is a share, not 0.17 points.
        if match is not None and match.group(2):
            if whole <= 0:
                raise ConfigError(f"{field}: cannot measure {value!r} against nothing")
            # The same licence as below: tracking written as '-0.4pt' is a share
            # measured in points, and just as legitimately negative.
            return to_points(value, field, positive=positive) / whole

    if not positive:
        ratio = _plain_number(value, field)
        if abs(ratio) > _RATIO_CEILING:
            raise ConfigError(
                f"{field}: {value!r} is not a usable share",
                hint="Use a fraction such as 0.002, a percentage, or a length "
                "such as '0.4pt'.",
            )
        return ratio

    return to_ratio(value, field)


def to_alpha(value: str | Number, field: str) -> float:
    """Return ``value`` as a share from nought to one.

    ``"35%"`` and ``0.35`` are the same thing. Unlike :func:`to_ratio`, nought
    is allowed and means none of it — which is what a setting that is off by
    default has to be able to say — and anything above one is refused, because
    there is no more than all of it.
    """
    ratio = _plain_number(value, field, hint=_ALPHA_HINT)
    if not 0.0 <= ratio <= 1.0:
        raise ConfigError(
            f"{field}: {value!r} is not a share between nought and one",
            hint=_ALPHA_HINT,
        )
    return ratio


def _plain_number(
    value: str | Number, field: str, hint: str = _SHARE_HINT
) -> float:
    """A share with no bound on its sign, for tracking and the like."""
    if isinstance(value, bool):
        raise ConfigError(f"{field}: expected a share, got a boolean")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        match = _RATIO_RE.match(value)
        if match is not None:
            ratio = float(match.group(1))
            return ratio / 100.0 if match.group(2) else ratio
    raise ConfigError(f"{field}: expected a share, got {value!r}", hint=hint)


def to_colour(value: object, field: str) -> str:
    """Validate a ``#rgb`` / ``#rrggbb`` / ``#rrggbbaa`` colour and return it."""
    if not isinstance(value, str) or not _HEX_COLOUR_RE.match(value):
        raise ConfigError(
            f"{field}: {value!r} is not a colour",
            hint="Use a hexadecimal colour such as '#f5f5f7', '#fff' or '#00000080'.",
        )
    return value


def _custom_size_hint(field: str) -> str:
    """Show where a width and height are written, for the setting that failed.

    The pair replaces the *name*, under the same key — which is the half a
    reader told only to "give a width and height instead" has to guess, and
    the natural guess is a `width:` beside `size:`, refused as an unknown
    setting by a different part of the program. Built from ``field`` rather
    than written out, so the shape shown is always the one that failed.
    """
    lines, indent = [], ""
    for part in field.split("."):
        lines.append(f"{indent}{part}:")
        indent += "  "
    lines += [f"{indent}width: 210mm", f"{indent}height: 297mm"]
    return "A width and height replace the name, under the same setting:\n" + "\n".join(
        f"  {line}" for line in lines
    )


def page_size(value: object, field: str) -> tuple[float, float]:
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
        raise ConfigError(
            f"{field}: expected a page size name or a width/height pair, got {value!r}",
            hint=_custom_size_hint(field),
        )

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
            hint=f"Known sizes: {known}. Append '-landscape' to rotate one.\n"
            + _custom_size_hint(field),
        )

    width_mm, height_mm = _PAGE_SIZES_MM[name]
    if landscape:
        width_mm, height_mm = height_mm, width_mm
    per_mm = _POINTS_PER_UNIT["mm"]
    return width_mm * per_mm, height_mm * per_mm
