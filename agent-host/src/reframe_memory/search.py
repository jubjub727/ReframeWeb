from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import re
from typing import Any


@dataclass(frozen=True)
class TagSearch:
    any_of: tuple[str, ...] = ()
    all_of: tuple[str, ...] = ()
    none_of: tuple[str, ...] = ()

    @classmethod
    def build(
        cls,
        *,
        any_of: Sequence[str] = (),
        all_of: Sequence[str] = (),
        none_of: Sequence[str] = (),
    ) -> "TagSearch":
        return cls(
            any_of=_clean_terms(any_of),
            all_of=_clean_terms(all_of),
            none_of=_clean_terms(none_of),
        )


@dataclass(frozen=True)
class StringSearch:
    contains: tuple[str, ...] = ()
    equals: tuple[str, ...] = ()

    @classmethod
    def build(
        cls,
        *,
        contains: Sequence[str] = (),
        equals: Sequence[str] = (),
    ) -> "StringSearch":
        return cls(
            contains=_clean_terms(contains),
            equals=_clean_terms(equals),
        )


@dataclass(frozen=True)
class MemoryNodeSearch:
    tags: TagSearch = TagSearch()
    strings: StringSearch = StringSearch()
    string_fields: tuple[str, ...] = ()
    content_contains: Mapping[str, tuple[str, ...]] | None = None
    content_equals: Mapping[str, tuple[str, ...]] | None = None


@dataclass(frozen=True)
class QueryParts:
    where_sql: str
    variables: dict[str, Any]


def build_memory_node_where(search: MemoryNodeSearch | None) -> QueryParts:
    if search is None:
        return QueryParts(where_sql="", variables={})

    clauses: list[str] = []
    variables: dict[str, Any] = {}

    _add_tag_clauses(clauses, variables, search.tags)
    _add_string_search_clause(
        clauses,
        variables,
        strings=search.strings,
        fields=search.string_fields,
    )
    _add_content_clauses(clauses, variables, search.content_contains or {})
    _add_content_equals_clauses(clauses, variables, search.content_equals or {})

    if not clauses:
        return QueryParts(where_sql="", variables={})

    return QueryParts(where_sql="WHERE " + " AND ".join(clauses), variables=variables)


def _add_tag_clauses(
    clauses: list[str],
    variables: dict[str, Any],
    tags: TagSearch,
) -> None:
    if tags.any_of:
        variables["tag_any_of"] = list(tags.any_of)
        clauses.append("array::len(array::intersect(tags, $tag_any_of)) > 0")

    if tags.all_of:
        variables["tag_all_of"] = list(tags.all_of)
        clauses.append(
            "array::len(array::intersect(tags, $tag_all_of)) = array::len($tag_all_of)"
        )

    if tags.none_of:
        variables["tag_none_of"] = list(tags.none_of)
        clauses.append("array::len(array::intersect(tags, $tag_none_of)) = 0")


def _add_content_clauses(
    clauses: list[str],
    variables: dict[str, Any],
    content_contains: Mapping[str, tuple[str, ...]],
) -> None:
    for index, (field, terms) in enumerate(content_contains.items()):
        _validate_content_field(field)
        clean_terms = _clean_terms(terms)
        if not clean_terms:
            continue

        term_clauses: list[str] = []
        for term_index, term in enumerate(clean_terms):
            variable_name = f"content_term_{index}_{term_index}"
            variables[variable_name] = term.lower()
            term_clauses.append(
                f"string::contains(string::lowercase(<string>content.{field}), ${variable_name})"
            )

        clauses.append("(" + " OR ".join(term_clauses) + ")")


def _add_content_equals_clauses(
    clauses: list[str],
    variables: dict[str, Any],
    content_equals: Mapping[str, tuple[str, ...]],
) -> None:
    for index, (field, values) in enumerate(content_equals.items()):
        _validate_content_field(field)
        clean_values = _clean_terms(values)
        if not clean_values:
            continue

        value_clauses: list[str] = []
        for value_index, value in enumerate(clean_values):
            variable_name = f"content_value_{index}_{value_index}"
            variables[variable_name] = value
            value_clauses.append(f"content.{field} = ${variable_name}")

        clauses.append("(" + " OR ".join(value_clauses) + ")")


def _add_string_search_clause(
    clauses: list[str],
    variables: dict[str, Any],
    *,
    strings: StringSearch,
    fields: Sequence[str],
) -> None:
    contains = _clean_terms(strings.contains)
    equals = _clean_terms(strings.equals)
    if not contains and not equals:
        return

    clean_fields = _clean_content_fields(fields)
    if not clean_fields:
        raise ValueError("string search requires at least one searchable content field")

    string_clauses: list[str] = []
    for field_index, field in enumerate(clean_fields):
        for term_index, term in enumerate(contains):
            variable_name = f"string_contains_{field_index}_{term_index}"
            variables[variable_name] = term.lower()
            string_clauses.append(
                f"string::contains(string::lowercase(<string>content.{field}), ${variable_name})"
            )

        for value_index, value in enumerate(equals):
            variable_name = f"string_equals_{field_index}_{value_index}"
            variables[variable_name] = value
            string_clauses.append(f"content.{field} = ${variable_name}")

    clauses.append("(" + " OR ".join(string_clauses) + ")")


def _clean_content_fields(fields: Sequence[str]) -> tuple[str, ...]:
    clean_fields = tuple(dict.fromkeys(field.strip() for field in fields if field.strip()))
    for field in clean_fields:
        _validate_content_field(field)
    return clean_fields


def _clean_terms(terms: Sequence[str]) -> tuple[str, ...]:
    return tuple(term.strip() for term in terms if term.strip())


def _validate_content_field(field: str) -> None:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*", field):
        msg = f"invalid content field path: {field!r}"
        raise ValueError(msg)
