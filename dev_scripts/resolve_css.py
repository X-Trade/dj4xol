#!/usr/bin/env python
"""
Resolve effective CSS declarations for a target element path.

This is a lightweight, dependency-free cascade resolver intended for local
theme debugging (e.g. "which rule wins for this element in this theme?").

Supported selector features:
- Type selectors, classes, ids, universal (*)
- Descendant and child combinators
- :not(...) with simple inner selectors (.class, #id, tag)
- Comma-separated selector groups

Unsupported/limited:
- Dynamic pseudo-classes (:hover, :focus, etc.) are ignored for matching.
- Attribute selectors and complex pseudo selectors are not fully evaluated.
- @media/@supports blocks are parsed recursively but conditions are not
  evaluated; nested rules are always included.

Example:
  python dev_scripts/resolve_css.py \
    --css dj4xol/static/dj4xol/css/theme.css \
    --css dj4xol/static/dj4xol/css/theme-lcars.css \
    --path "body.email-theme-lcars div.email-panel div.email-panel-header" \
    --show-all
"""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
STYLE_BLOCK_RE = re.compile(r"<style[^>]*>(.*?)</style>", re.I | re.S)
DECL_NAME_RE = re.compile(r"^-?[a-zA-Z_][a-zA-Z0-9_-]*$")
SEGMENT_SPLIT_RE = re.compile(r"\s*>\s*|\s+")


@dataclass
class Rule:
    selector: str
    declarations: List[Tuple[str, str, bool]]
    specificity: Tuple[int, int, int]
    order: int
    source: str
    line: int


@dataclass
class Node:
    tag: str
    id: str
    classes: set


def _strip_comments(css_text: str) -> str:
    return COMMENT_RE.sub("", css_text)


def _split_top_level_commas(selector_group: str) -> List[str]:
    out: List[str] = []
    start = 0
    depth_paren = 0
    depth_bracket = 0
    in_quote: Optional[str] = None
    for i, ch in enumerate(selector_group):
        if in_quote:
            if ch == in_quote:
                in_quote = None
            continue
        if ch in ("'", '"'):
            in_quote = ch
            continue
        if ch == "(":
            depth_paren += 1
        elif ch == ")":
            depth_paren = max(0, depth_paren - 1)
        elif ch == "[":
            depth_bracket += 1
        elif ch == "]":
            depth_bracket = max(0, depth_bracket - 1)
        elif ch == "," and depth_paren == 0 and depth_bracket == 0:
            piece = selector_group[start:i].strip()
            if piece:
                out.append(piece)
            start = i + 1
    tail = selector_group[start:].strip()
    if tail:
        out.append(tail)
    return out


def _find_matching_brace(text: str, open_idx: int) -> int:
    depth = 0
    in_quote: Optional[str] = None
    i = open_idx
    while i < len(text):
        ch = text[i]
        if in_quote:
            if ch == in_quote:
                in_quote = None
            i += 1
            continue
        if ch in ("'", '"'):
            in_quote = ch
            i += 1
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _line_number(text: str, idx: int) -> int:
    return text.count("\n", 0, idx) + 1


def _split_declarations(block: str) -> List[str]:
    parts: List[str] = []
    start = 0
    depth_paren = 0
    depth_bracket = 0
    in_quote: Optional[str] = None
    for i, ch in enumerate(block):
        if in_quote:
            if ch == in_quote:
                in_quote = None
            continue
        if ch in ("'", '"'):
            in_quote = ch
            continue
        if ch == "(":
            depth_paren += 1
        elif ch == ")":
            depth_paren = max(0, depth_paren - 1)
        elif ch == "[":
            depth_bracket += 1
        elif ch == "]":
            depth_bracket = max(0, depth_bracket - 1)
        elif ch == ";" and depth_paren == 0 and depth_bracket == 0:
            piece = block[start:i].strip()
            if piece:
                parts.append(piece)
            start = i + 1
    tail = block[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def _parse_declarations(block: str) -> List[Tuple[str, str, bool]]:
    out: List[Tuple[str, str, bool]] = []
    for decl in _split_declarations(block):
        if ":" not in decl:
            continue
        name, value = decl.split(":", 1)
        name = name.strip().lower()
        value = value.strip()
        if not DECL_NAME_RE.match(name):
            continue
        important = False
        if re.search(r"!\s*important\s*$", value, re.I):
            important = True
            value = re.sub(r"!\s*important\s*$", "", value, flags=re.I).strip()
        out.append((name, value, important))
    return out


def _parse_rules_from_css(css_text: str, source: str, order_offset: int = 0) -> List[Rule]:
    css_text = _strip_comments(css_text)
    rules: List[Rule] = []
    order = order_offset
    i = 0
    n = len(css_text)
    while i < n:
        open_idx = css_text.find("{", i)
        if open_idx < 0:
            break
        selector_text = css_text[i:open_idx].strip()
        close_idx = _find_matching_brace(css_text, open_idx)
        if close_idx < 0:
            break
        block = css_text[open_idx + 1:close_idx]
        line = _line_number(css_text, open_idx)
        if selector_text.startswith("@"):
            at_name = selector_text.split(None, 1)[0].lower()
            if at_name in ("@media", "@supports", "@layer", "@document"):
                nested = _parse_rules_from_css(block, source, order)
                rules.extend(nested)
                order += len(nested)
            i = close_idx + 1
            continue

        decls = _parse_declarations(block)
        if decls:
            for selector in _split_top_level_commas(selector_text):
                spec = _specificity(selector)
                rules.append(
                    Rule(
                        selector=selector,
                        declarations=decls,
                        specificity=spec,
                        order=order,
                        source=source,
                        line=line,
                    )
                )
                order += 1
        i = close_idx + 1
    return rules


def _tokenise_selector(selector: str) -> Tuple[List[str], List[str]]:
    segments: List[str] = []
    combinators: List[str] = []
    buf: List[str] = []
    depth_paren = 0
    depth_bracket = 0
    in_quote: Optional[str] = None
    last_was_space = False

    def flush_buf() -> None:
        s = "".join(buf).strip()
        if s:
            segments.append(s)
        buf[:] = []

    for ch in selector.strip():
        if in_quote:
            buf.append(ch)
            if ch == in_quote:
                in_quote = None
            continue
        if ch in ("'", '"'):
            buf.append(ch)
            in_quote = ch
            continue
        if ch == "(":
            buf.append(ch)
            depth_paren += 1
            continue
        if ch == ")":
            buf.append(ch)
            depth_paren = max(0, depth_paren - 1)
            continue
        if ch == "[":
            buf.append(ch)
            depth_bracket += 1
            continue
        if ch == "]":
            buf.append(ch)
            depth_bracket = max(0, depth_bracket - 1)
            continue
        if depth_paren == 0 and depth_bracket == 0:
            if ch == ">":
                flush_buf()
                if segments:
                    combinators.append(">")
                last_was_space = False
                continue
            if ch.isspace():
                flush_buf()
                if segments and not last_was_space:
                    combinators.append(" ")
                last_was_space = True
                continue
        buf.append(ch)
        last_was_space = False
    flush_buf()
    while len(combinators) > max(0, len(segments) - 1):
        combinators.pop()
    return segments, combinators


def _parse_compound_selector(segment: str) -> Dict[str, object]:
    has_pseudo_element = bool(re.search(r"::[a-zA-Z-]+(?:\([^)]*\))?", segment))
    has_dynamic_pseudo = bool(
        re.search(r":(?!not\()[a-zA-Z-]+(?:\([^)]*\))?", segment)
    )

    # Remove pseudo-elements and pseudo-classes for base matching.
    cleaned = re.sub(r"::?[a-zA-Z-]+(?:\([^)]*\))?", "", segment)
    # But keep :not(...) by extracting before cleanup.
    nots = re.findall(r":not\(([^)]*)\)", segment)

    tag = "*"
    m = re.match(r"^[a-zA-Z][a-zA-Z0-9_-]*|\*", cleaned)
    if m:
        tag = m.group(0).lower()
    id_matches = re.findall(r"#([a-zA-Z_][a-zA-Z0-9_-]*)", cleaned)
    class_matches = re.findall(r"\.([a-zA-Z_][a-zA-Z0-9_-]*)", cleaned)
    return {
        "tag": tag,
        "id": id_matches[0] if id_matches else "",
        "classes": set(class_matches),
        "nots": [n.strip() for n in nots if n.strip()],
        "has_pseudo_element": has_pseudo_element,
        "has_dynamic_pseudo": has_dynamic_pseudo,
    }


def _match_simple_selector(simple: str, node: Node) -> bool:
    p = _parse_compound_selector(simple)
    if p["has_pseudo_element"]:
        return False
    if p["has_dynamic_pseudo"] and p["tag"] == "*" and not p["id"] and not p["classes"]:
        # Selectors like :hover / :root / ::-webkit-scrollbar-thumb should
        # not become universal matches in this simplified resolver.
        return False
    tag = p["tag"]  # type: ignore[assignment]
    if tag != "*" and tag != node.tag:
        return False
    sel_id = p["id"]  # type: ignore[assignment]
    if sel_id and sel_id != node.id:
        return False
    classes = p["classes"]  # type: ignore[assignment]
    if not classes.issubset(node.classes):
        return False
    for not_sel in p["nots"]:  # type: ignore[index]
        # Only evaluate simple :not() values (tag/.class/#id).
        if re.search(r"\s|>", not_sel):
            continue
        if _match_simple_selector(not_sel, node):
            return False
    return True


def _selector_matches_path(selector: str, path: Sequence[Node]) -> bool:
    segments, combinators = _tokenise_selector(selector)
    if not segments or not path:
        return False
    node_idx = len(path) - 1
    seg_idx = len(segments) - 1
    if not _match_simple_selector(segments[seg_idx], path[node_idx]):
        return False
    seg_idx -= 1

    while seg_idx >= 0:
        comb = combinators[seg_idx] if seg_idx < len(combinators) else " "
        if comb == ">":
            node_idx -= 1
            if node_idx < 0:
                return False
            if not _match_simple_selector(segments[seg_idx], path[node_idx]):
                return False
            seg_idx -= 1
            continue
        # Descendant combinator.
        found = False
        probe = node_idx - 1
        while probe >= 0:
            if _match_simple_selector(segments[seg_idx], path[probe]):
                node_idx = probe
                found = True
                break
            probe -= 1
        if not found:
            return False
        seg_idx -= 1
    return True


def _specificity(selector: str) -> Tuple[int, int, int]:
    # Crude but useful specificity calculator for common selectors.
    # IDs
    a = len(re.findall(r"#[a-zA-Z_][a-zA-Z0-9_-]*", selector))
    # Classes/attributes/pseudo-classes (including :not(...) container)
    b = len(re.findall(r"\.[a-zA-Z_][a-zA-Z0-9_-]*", selector))
    b += len(re.findall(r"\[[^\]]+\]", selector))
    b += len(re.findall(r":(?!:)[a-zA-Z-]+(?:\([^)]*\))?", selector))
    # Type selectors and pseudo-elements
    # Ignore universal and combinators/punctuation.
    stripped = re.sub(r"\[[^\]]+\]", " ", selector)
    stripped = re.sub(r"#[a-zA-Z_][a-zA-Z0-9_-]*", " ", stripped)
    stripped = re.sub(r"\.[a-zA-Z_][a-zA-Z0-9_-]*", " ", stripped)
    stripped = re.sub(r":{1,2}[a-zA-Z-]+(?:\([^)]*\))?", " ", stripped)
    candidates = re.findall(r"\b[a-zA-Z][a-zA-Z0-9_-]*\b", stripped)
    c = len([x for x in candidates if x.lower() not in ("not",)])
    return (a, b, c)


def _parse_path(path_str: str) -> List[Node]:
    raw_segments = [s for s in SEGMENT_SPLIT_RE.split(path_str.strip()) if s]
    nodes: List[Node] = []
    for seg in raw_segments:
        tag = "*"
        seg_work = seg
        m = re.match(r"^[a-zA-Z][a-zA-Z0-9_-]*|\*", seg_work)
        if m:
            tag = m.group(0).lower()
            seg_work = seg_work[m.end():]
        id_match = re.search(r"#([a-zA-Z_][a-zA-Z0-9_-]*)", seg_work)
        classes = set(re.findall(r"\.([a-zA-Z_][a-zA-Z0-9_-]*)", seg_work))
        node = Node(tag=tag, id=id_match.group(1) if id_match else "", classes=classes)
        nodes.append(node)
    return nodes


def _load_css_inputs(css_paths: Sequence[str]) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    for path in css_paths:
        abs_path = os.path.abspath(path)
        with open(abs_path, "r", encoding="utf-8") as f:
            text = f.read()
        if abs_path.lower().endswith(".html"):
            matches = STYLE_BLOCK_RE.findall(text)
            css_text = "\n\n".join(matches)
            label = "%s:<style>" % abs_path
            out.append((label, css_text))
        else:
            out.append((abs_path, text))
    return out


def _resolve(
    rules: Sequence[Rule],
    path: Sequence[Node],
) -> Tuple[Dict[str, str], Dict[str, Dict[str, object]], List[Rule]]:
    matched: List[Rule] = [r for r in rules if _selector_matches_path(r.selector, path)]
    winners: Dict[str, Dict[str, object]] = {}

    for rule in matched:
        for prop, value, important in rule.declarations:
            candidate = {
                "value": value,
                "important": important,
                "specificity": rule.specificity,
                "order": rule.order,
                "selector": rule.selector,
                "source": rule.source,
                "line": rule.line,
            }
            current = winners.get(prop)
            if current is None:
                winners[prop] = candidate
                continue
            cur_key = (
                1 if current["important"] else 0,
                current["specificity"],
                current["order"],
            )
            new_key = (
                1 if important else 0,
                rule.specificity,
                rule.order,
            )
            if new_key >= cur_key:
                winners[prop] = candidate

    final = {k: str(v["value"]) for k, v in sorted(winners.items())}
    return final, winners, matched


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--css",
        action="append",
        required=True,
        help="CSS or HTML file to load (repeatable). For HTML, style blocks are extracted.",
    )
    parser.add_argument(
        "--path",
        required=True,
        help=(
            "Ancestor path ending in target element, e.g. "
            "'body.email-theme-lcars div.email-panel div.email-panel-header'"
        ),
    )
    parser.add_argument(
        "--prop",
        action="append",
        help="Only print selected property name(s). Repeatable.",
    )
    parser.add_argument(
        "--show-all",
        action="store_true",
        help="Show winning declarations with selector/source metadata.",
    )
    parser.add_argument(
        "--show-matched-selectors",
        action="store_true",
        help="Also list all selectors that matched the target path.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output resolved data as JSON.",
    )
    args = parser.parse_args()

    path = _parse_path(args.path)
    if not path:
        raise SystemExit("No valid path segments parsed from --path")

    css_inputs = _load_css_inputs(args.css)
    rules: List[Rule] = []
    order = 0
    for source, css_text in css_inputs:
        parsed = _parse_rules_from_css(css_text, source, order_offset=order)
        rules.extend(parsed)
        order += len(parsed)

    resolved, winners, matched = _resolve(rules, path)
    props_filter = {p.strip().lower() for p in (args.prop or []) if p.strip()}
    if props_filter:
        resolved = {k: v for k, v in resolved.items() if k in props_filter}

    if args.json:
        payload = {"resolved": resolved}
        if args.show_all:
            details = {}
            for prop, info in winners.items():
                if props_filter and prop not in props_filter:
                    continue
                details[prop] = info
            payload["winners"] = details
        if args.show_matched_selectors:
            payload["matched_selectors"] = [
                {
                    "selector": r.selector,
                    "specificity": r.specificity,
                    "source": r.source,
                    "line": r.line,
                }
                for r in matched
            ]
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    print("Target path: %s" % args.path)
    print("Rules loaded: %d | Rules matched: %d" % (len(rules), len(matched)))
    print("")
    print("Resolved properties:")
    for prop, value in sorted(resolved.items()):
        print("  %s: %s" % (prop, value))

    if args.show_all:
        print("")
        print("Winning declarations:")
        for prop in sorted(resolved.keys()):
            info = winners[prop]
            print(
                "  %s: %s  [%s @ %s:%s spec=%s%s]"
                % (
                    prop,
                    info["value"],
                    info["selector"],
                    info["source"],
                    info["line"],
                    info["specificity"],
                    " !important" if info["important"] else "",
                )
            )

    if args.show_matched_selectors:
        print("")
        print("Matched selectors:")
        for r in matched:
            print(
                "  %s  [spec=%s @ %s:%s]"
                % (r.selector, r.specificity, r.source, r.line)
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
