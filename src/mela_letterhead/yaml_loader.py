"""Reading YAML the way a hand-edited file deserves to be read.

PyYAML takes the last of two keys spelled the same way and says nothing about
it. That is the YAML specification's business and not a bug in PyYAML, but it
is the one remaining way to get a page you did not ask for out of a
configuration that ``check`` calls clean::

    header:
      height: 30mm      # what you just added, at the top of the section
      show: true
      height: 43mm      # what was already there, twelve lines down

Nothing there is wrong by YAML's reckoning, so nothing is reported, and the
band is 43mm. The setting the user just wrote is discarded in silence — in a
file of three hundred lines that people edit by scrolling and inserting, which
is exactly how the second spelling gets written in the first place.

:class:`Loader` refuses it instead, and the three files a user edits by hand —
the configuration, a document's front matter and a locale pack — are all read
through :func:`load`.

Merge keys are untouched. The check runs over the keys as written, before
PyYAML flattens a ``<<`` into them, so a mapping that deliberately overrides
something it merged in is still legal — which is the whole point of merging.
"""

from __future__ import annotations

from typing import Any, Dict

import yaml

#: Said the same way wherever a duplicate is reported, because the advice does
#: not change with the file it is about.
DUPLICATE_KEY_HINT = (
    "The second one wins, which is rarely what somebody means by writing both. "
    "Delete whichever is not wanted."
)


class DuplicateKeyError(yaml.MarkedYAMLError):
    """A mapping sets the same key twice.

    Derived from PyYAML's own error, so a caller that knows only about
    ``yaml.YAMLError`` still reports this as a message rather than letting it
    out as a traceback. The attributes are for the callers that would rather
    say it in their own words, and in terms of their own file.
    """

    def __init__(self, key: Any, first: yaml.Mark, second: yaml.Mark) -> None:
        super().__init__(
            context=f"the key {key!r} is set twice",
            context_mark=first,
            problem="and this second one is the one that would win",
            problem_mark=second,
        )
        self.key = key
        # PyYAML counts lines from nought; everybody else counts from one.
        self.first_line = first.line + 1
        self.second_line = second.line + 1


class Loader(yaml.SafeLoader):
    """``yaml.SafeLoader``, plus a refusal to read the same key twice."""

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> Dict[Any, Any]:
        seen: Dict[Any, yaml.Mark] = {}
        for key_node, _ in node.value:
            # Constructed rather than read off the node, because YAML says
            # `yes` and `true` are the same key and the raw text does not.
            # `construct_object` carries no annotation in types-PyYAML; what it
            # returns is whatever the file says, which is `Any` regardless.
            try:
                key = self.construct_object(key_node, deep=deep)  # type: ignore[no-untyped-call]
            except yaml.constructor.ConstructorError:
                # A key with no constructor of its own. `<<` is the one that
                # matters — PyYAML resolves a merge in `flatten_mapping` below
                # rather than by constructing it — and anything else here is
                # the base class's to refuse, in its own words, a moment later.
                continue
            try:
                first = seen.get(key)
            except TypeError:
                # A key that cannot be hashed cannot be compared either. The
                # base class refuses it by name a moment later; leave it that.
                continue
            if first is not None:
                raise DuplicateKeyError(key, first, key_node.start_mark)
            seen[key] = key_node.start_mark
        return super().construct_mapping(node, deep=deep)


def load(text: str) -> Any:
    """``yaml.safe_load``, refusing a mapping that sets the same key twice."""
    return yaml.load(text, Loader)
