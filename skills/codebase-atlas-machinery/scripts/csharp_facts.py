"""Conservative, standard-library C# source-fact extraction for Codebase Atlas."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any


EXTRACTION_METHOD = "csharp-lexical-facts-v7"
SUPPORTED_FORMS = [
    "namespace-scoped class and interface declarations",
    "class primary-constructor parameters with literal type expressions",
    "method declarations with block or expression bodies",
    "Route and HttpGet/HttpPost/HttpPut/HttpDelete/HttpPatch attributes with literal arguments",
    "receiver-name invocation syntax within method bodies, without binding calls to parameters",
    "generic AddScoped/AddTransient/AddSingleton and TryAdd* registrations with exactly two type arguments",
    "regular, escaped, verbatim, and single-line raw string literals",
]
LIMITATIONS = [
    "This is source-fact extraction, not a C# compiler or general call-target resolver.",
    "Type expressions are preserved as observed syntax; name matches are candidate records and never resolved cross-file links.",
    "Conditional directives, interpolated literals in relevant syntax, unsupported declarations, and shadowed receiver names produce unresolved evidence.",
    "Receiver-name invocation syntax is not bound to constructor parameters; lambda and other local scopes are not resolved.",
    "Only direct generic two-type dependency registrations are represented; factories, reflection, generated registrations, and runtime configuration are not resolved.",
]


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    start: int
    end: int
    line: int
    column: int
    end_line: int
    end_column: int


def _advance(text: str, line: int, column: int) -> tuple[int, int]:
    for char in text:
        if char == "\n":
            line, column = line + 1, 1
        else:
            column += 1
    return line, column


def _decode_regular_string(raw: str) -> str | None:
    result: list[str] = []
    i = 0
    escapes = {"0": "\0", "a": "\a", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v", "\\": "\\", '"': '"', "'": "'"}
    while i < len(raw):
        if raw[i] != "\\":
            result.append(raw[i])
            i += 1
            continue
        i += 1
        if i >= len(raw):
            return None
        code = raw[i]
        if code in escapes:
            result.append(escapes[code])
            i += 1
        elif code in ("u", "U"):
            width = 4 if code == "u" else 8
            digits = raw[i + 1:i + 1 + width]
            if len(digits) != width or not re.fullmatch(r"[0-9A-Fa-f]+", digits):
                return None
            try:
                result.append(chr(int(digits, 16)))
            except ValueError:
                return None
            i += 1 + width
        elif code == "x":
            match = re.match(r"[0-9A-Fa-f]{1,4}", raw[i + 1:])
            if not match:
                return None
            result.append(chr(int(match.group(0), 16)))
            i += 1 + len(match.group(0))
        else:
            return None
    return "".join(result)


def lex(text: str) -> tuple[list[Token], list[Token]]:
    """Return code tokens and directive tokens; comments and literal bodies are opaque."""
    tokens: list[Token] = []
    directives: list[Token] = []
    i, line, column = 0, 1, 1
    multi = ("=>", "::", "?.", "??", "==", "!=", "<=", ">=", "++", "--", "&&", "||", "+=", "-=", "??=")
    while i < len(text):
        start, start_line, start_column = i, line, column
        char = text[i]
        if char.isspace():
            consumed = char
            i += 1
            line, column = _advance(consumed, line, column)
            continue
        line_start = text.rfind("\n", 0, i) + 1
        if char == "#" and not text[line_start:i].strip():
            end = text.find("\n", i)
            if end < 0:
                end = len(text)
            value = text[i:end]
            directives.append(Token("directive", value, i, end, line, column, line, column + len(value)))
            i = end
            line, column = _advance(value, line, column)
            continue
        if text.startswith("//", i):
            end = text.find("\n", i)
            if end < 0:
                end = len(text)
            consumed = text[i:end]
            i = end
            line, column = _advance(consumed, line, column)
            continue
        if text.startswith("/*", i):
            end = text.find("*/", i + 2)
            end = len(text) if end < 0 else end + 2
            consumed = text[i:end]
            i = end
            line, column = _advance(consumed, line, column)
            continue

        # C# regular, verbatim, interpolated, and raw strings.
        prefix = ""
        quote_at = i
        while quote_at < len(text) and text[quote_at] in "$@":
            prefix += text[quote_at]
            quote_at += 1
        is_string = quote_at < len(text) and text[quote_at] == '"' and (quote_at > i or char == '"')
        if is_string:
            quote_count = 1
            while quote_at + quote_count < len(text) and text[quote_at + quote_count] == '"':
                quote_count += 1
            interpolated = "$" in prefix
            verbatim = "@" in prefix
            if interpolated and quote_count < 3:
                cursor = quote_at + 1
                brace_depth = 0
                while cursor < len(text):
                    current = text[cursor]
                    if brace_depth and current == '"':
                        cursor += 1
                        while cursor < len(text):
                            if not verbatim and text[cursor] == "\\":
                                cursor += 2
                            elif text[cursor] == '"':
                                if verbatim and cursor + 1 < len(text) and text[cursor + 1] == '"':
                                    cursor += 2
                                else:
                                    cursor += 1
                                    break
                            else:
                                cursor += 1
                        continue
                    if current == "{" and cursor + 1 < len(text) and text[cursor + 1] == "{":
                        cursor += 2
                        continue
                    if current == "}" and cursor + 1 < len(text) and text[cursor + 1] == "}":
                        cursor += 2
                        continue
                    if current == "{":
                        brace_depth += 1
                    elif current == "}" and brace_depth:
                        brace_depth -= 1
                    elif current == '"' and brace_depth == 0:
                        break
                    elif current == "\\" and not verbatim:
                        cursor += 1
                    cursor += 1
                end = min(len(text), cursor + 1)
                consumed = text[i:end]
                tokens.append(Token("interpolated_literal", "", start, end, start_line, start_column, *_advance(consumed, start_line, start_column)))
                i = end
                line, column = _advance(consumed, line, column)
                continue
            if quote_count >= 3:
                closing = '"' * quote_count
                end = text.find(closing, quote_at + quote_count)
                if end < 0:
                    end = len(text)
                    value = None
                else:
                    value = None if interpolated else text[quote_at + quote_count:end]
                    end += quote_count
                    if value is not None and value.startswith("\n"):
                        value = value[1:]
                    if value is not None and value.endswith("\n"):
                        value = value[:-1]
                    kind = "interpolated_literal" if interpolated else "raw_literal"
            else:
                cursor = quote_at + 1
                chunks: list[str] = []
                while cursor < len(text):
                    current = text[cursor]
                    if current == '"':
                        if verbatim and cursor + 1 < len(text) and text[cursor + 1] == '"':
                            chunks.append('"')
                            cursor += 2
                            continue
                        break
                    if not verbatim and current == "\\" and cursor + 1 < len(text):
                        chunks.append(text[cursor:cursor + 2])
                        cursor += 2
                        continue
                    chunks.append(current)
                    cursor += 1
                end = min(len(text), cursor + 1)
                raw = "".join(chunks)
                value = None if interpolated else (raw if verbatim else _decode_regular_string(raw))
                kind = "interpolated_literal" if interpolated else "literal"
            consumed = text[i:end]
            tokens.append(Token(kind, value if value is not None else "", start, end, start_line, start_column, *_advance(consumed, start_line, start_column)))
            i = end
            line, column = _advance(consumed, line, column)
            continue

        if char == "'":
            cursor = i + 1
            while cursor < len(text):
                if text[cursor] == "\\":
                    cursor += 2
                    continue
                if text[cursor] == "'":
                    cursor += 1
                    break
                cursor += 1
            consumed = text[i:cursor]
            tokens.append(Token("char", "", i, cursor, line, column, *_advance(consumed, line, column)))
            i = cursor
            line, column = _advance(consumed, line, column)
            continue

        match = re.match(r"(?:@?[A-Za-z_][A-Za-z0-9_]*|[0-9]+(?:\.[0-9]+)?)", text[i:])
        if match:
            value = match.group(0)
            kind = "identifier" if value[0].isalpha() or value[0] == "_" or value.startswith("@") else "number"
            end = i + len(value)
        else:
            value = next((item for item in multi if text.startswith(item, i)), char)
            kind = "punctuation"
            end = i + len(value)
        consumed = text[i:end]
        tokens.append(Token(kind, value, i, end, line, column, *_advance(consumed, line, column)))
        i = end
        line, column = _advance(consumed, line, column)
    return tokens, directives


def _matches(tokens: list[Token]) -> dict[int, int]:
    pairs = {"(": ")", "[": "]", "{": "}"}
    openers: list[tuple[str, int]] = []
    result: dict[int, int] = {}
    for index, token in enumerate(tokens):
        if token.value in pairs:
            openers.append((token.value, index))
        elif token.value in pairs.values() and openers and pairs[openers[-1][0]] == token.value:
            _, start = openers.pop()
            result[start] = index
            result[index] = start
    return result


def _split_top(tokens: list[Token], start: int, end: int) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    depth_angle = depth_paren = depth_bracket = depth_brace = 0
    part = start
    for index in range(start, end):
        value = tokens[index].value
        if value == "<": depth_angle += 1
        elif value == ">" and depth_angle: depth_angle -= 1
        elif value == "(": depth_paren += 1
        elif value == ")" and depth_paren: depth_paren -= 1
        elif value == "[": depth_bracket += 1
        elif value == "]" and depth_bracket: depth_bracket -= 1
        elif value == "{": depth_brace += 1
        elif value == "}" and depth_brace: depth_brace -= 1
        elif value == "," and not (depth_angle or depth_paren or depth_bracket or depth_brace):
            result.append((part, index))
            part = index + 1
    if part < end:
        result.append((part, end))
    return result


def _type_text(tokens: list[Token], start: int, end: int) -> str:
    return "".join(token.value for token in tokens[start:end])


def _parameter_parts(tokens: list[Token], start: int, end: int, matches: dict[int, int]) -> tuple[str, str] | None:
    while start < end and tokens[start].value in {"this", "scoped", "ref", "out", "in", "params", "readonly"}:
        start += 1
    while start < end and tokens[start].value == "[" and start in matches:
        start = matches[start] + 1
    depth = 0
    for i in range(start, end):
        if tokens[i].value in ("<", "(", "["): depth += 1
        elif tokens[i].value in (">", ")", "]") and depth: depth -= 1
        elif tokens[i].value == "=" and depth == 0:
            end = i
            break
    identifiers = [i for i in range(start, end) if tokens[i].kind == "identifier"]
    if len(identifiers) < 2:
        return None
    name_index = identifiers[-1]
    return _type_text(tokens, start, name_index), tokens[name_index].value.lstrip("@")


def _generic_args(tokens: list[Token], start: int, matches_angle: dict[int, int]) -> tuple[list[tuple[int, int]], int] | None:
    if start >= len(tokens) or tokens[start].value != "<" or start not in matches_angle:
        return None
    end = matches_angle[start]
    return _split_top(tokens, start + 1, end), end


def _angle_matches(tokens: list[Token]) -> dict[int, int]:
    stack: list[int] = []
    matches: dict[int, int] = {}
    for i, token in enumerate(tokens):
        if token.value == "<":
            stack.append(i)
        elif token.value == ">" and stack:
            start = stack.pop()
            matches[start] = i
    return matches


def _namespace_at(tokens: list[Token], index: int, braces: dict[int, int]) -> str:
    active: list[tuple[int, int | None, str]] = []
    for i, token in enumerate(tokens[:index]):
        if token.value != "namespace":
            continue
        cursor = i + 1
        while cursor < index and tokens[cursor].value not in (";", "{"):
            cursor += 1
        if cursor >= index:
            continue
        name = _type_text(tokens, i + 1, cursor)
        if tokens[cursor].value == ";":
            active = [(i, None, name)]
        elif cursor in braces and braces[cursor] > index:
            active.append((i, braces[cursor], name))
    return ".".join(item[2] for item in active if item[1] is None or item[1] > index)


def _source_ref(path: str, source_hash: str, tokens: list[Token], start: int, end: int) -> dict[str, Any]:
    first = tokens[start]
    last = tokens[end - 1] if end > start else first
    return {
        "path": path,
        "sha256": source_hash,
        "span": {
            "start_offset": first.start,
            "end_offset": last.end,
            "offset_unit": "unicode_codepoint",
            "start_line": first.line,
            "start_column": first.column,
            "end_line": last.end_line,
            "end_column": last.end_column,
        },
    }


def _stable_id(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")
    return hashlib.sha256(raw).hexdigest()[:24]


def _header_start(tokens: list[Token], index: int, lower_bound: int) -> int:
    cursor = index - 1
    while cursor >= lower_bound and tokens[cursor].value not in (";", "{", "}"):
        cursor -= 1
    return cursor + 1


def _attributes(tokens: list[Token], start: int, end: int, matches: dict[int, int]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    i = start
    while i < end:
        if tokens[i].value != "[" or i not in matches or matches[i] >= end:
            i += 1
            continue
        close = matches[i]
        inside = tokens[i + 1:close]
        if not inside or inside[0].kind != "identifier":
            i = close + 1
            continue
        name_parts = [inside[0].value.lstrip("@")]
        cursor = 1
        while cursor + 1 < len(inside) and inside[cursor].value == "." and inside[cursor + 1].kind == "identifier":
            name_parts.append(inside[cursor + 1].value.lstrip("@"))
            cursor += 2
        attr: dict[str, Any] = {
            "name": ".".join(name_parts),
            "start": i,
            "end": close + 1,
            "arguments": [],
        }
        if cursor < len(inside) and inside[cursor].value == "(" and cursor in _matches(inside):
            close_paren = _matches(inside)[cursor]
            for a, b in _split_top(inside, cursor + 1, close_paren):
                attr["arguments"].append((inside, a, b))
        result.append(attr)
        i = close + 1
    return result


def _literal_arg(arg_tokens: list[Token], start: int, end: int) -> tuple[str | None, str | None]:
    if end - start == 1 and arg_tokens[start].kind == "literal":
        return arg_tokens[start].value, None
    if end - start == 1 and arg_tokens[start].kind == "raw_literal":
        if "\n" in arg_tokens[start].value or "\r" in arg_tokens[start].value:
            return None, "multiline raw route literal indentation is unsupported"
        return arg_tokens[start].value, None
    if any(arg_tokens[i].kind == "interpolated_literal" for i in range(start, end)):
        return None, "interpolated literal is not a fixed route value"
    return None, "route argument is not one supported string literal"


def _param_list(tokens: list[Token], start: int, end: int, matches: dict[int, int]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for part_start, part_end in _split_top(tokens, start, end):
        parsed = _parameter_parts(tokens, part_start, part_end, matches)
        if parsed is not None:
            type_expr, name = parsed
            result.append({"name": name, "type_expression": type_expr, "start": part_start, "end": part_end})
    return result


def _method_shadowed(tokens: list[Token], start: int, end: int, name: str, method_params: list[dict[str, Any]]) -> bool:
    if any(parameter["name"] == name for parameter in method_params):
        return True
    for i in range(start, end):
        if tokens[i].value == "foreach" and i + 1 < end and tokens[i + 1].value == "(":
            close = i + 1
            depth = 1
            while close + 1 < end and depth:
                close += 1
                if tokens[close].value == "(": depth += 1
                elif tokens[close].value == ")": depth -= 1
            header = tokens[i + 2:close]
            if any(token.value.lstrip("@") == name for token in header[:next((n for n, token in enumerate(header) if token.value == "in"), len(header))][-1:]):
                return True
        if tokens[i].kind != "identifier" or tokens[i].value.lstrip("@") != name:
            continue
        previous = tokens[i - 1].value if i > start else ""
        following = tokens[i + 1].value if i + 1 < end else ""
        next_two = tokens[i + 2].value if i + 2 < end else ""
        if following == "=>" or (following == ")" and next_two == "=>" and previous != ""):
            return True
        if following == "=" and (previous in {"var", "const", "using", "await"} or (i > start and tokens[i - 1].kind == "identifier")):
            return True
    return False


def _using_aliases(tokens: list[Token]) -> set[str]:
    aliases: set[str] = set()
    for i in range(len(tokens) - 3):
        if tokens[i].value != "using":
            continue
        if tokens[i + 1].kind == "identifier" and tokens[i + 2].value == "=":
            aliases.add(tokens[i + 1].value.lstrip("@"))
    return aliases


def _type_uses_alias(expression: str, aliases: set[str]) -> bool:
    if not aliases:
        return False
    tokens, _ = lex(expression)
    expect_type_start = True
    for token in tokens:
        if token.value in {"<", ","}:
            expect_type_start = True
        elif token.value in {".", "::", "?", "[", "]", "*"}:
            continue
        elif expect_type_start and token.kind == "identifier":
            if token.value.lstrip("@") in aliases:
                return True
            expect_type_start = False
        elif token.value != "global":
            expect_type_start = False
    return False


def _candidate_base(expression: str) -> str:
    base = expression.split("<", 1)[0].replace("global::", "")
    return base.rsplit(".", 1)[-1].strip()


def _using_namespaces(tokens: list[Token]) -> tuple[set[str], bool]:
    """Read only compilation-unit `using Namespace;` directives."""
    namespaces: set[str] = set()
    first_namespace = next((i for i, token in enumerate(tokens) if token.value == "namespace"), len(tokens))
    unsupported = False
    i = 0
    while i < len(tokens):
        if tokens[i].value != "using":
            i += 1
            continue
        end = i + 1
        while end < len(tokens) and tokens[end].value != ";":
            end += 1
        directive = tokens[i + 1:end]
        if i > first_namespace or any(item.value in {"=", "static", "global"} for item in directive):
            unsupported = True
        elif directive and directive[0].kind == "identifier" and all(
            item.kind == "identifier" if n % 2 == 0 else item.value == "."
            for n, item in enumerate(directive)
        ):
            namespaces.add(_type_text(directive, 0, len(directive)))
        else:
            unsupported = True
        i = end + 1
    return namespaces, unsupported


def _parse_file(path: str, source: str, source_hash: str) -> dict[str, Any]:
    tokens, directives = lex(source)
    aliases = _using_aliases(tokens)
    imports, unsupported_imports = _using_namespaces(tokens)
    pairs = _matches(tokens)
    angle_pairs = _angle_matches(tokens)
    types: list[dict[str, Any]] = []
    facts: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    if directives:
        for directive in directives:
            unresolved.append({
                "kind": "preprocessor_directive",
                "reason": "file not analyzed because conditional compilation can change active declarations",
                "source": {
                    "path": path,
                    "sha256": source_hash,
                    "span": {
                        "start_offset": directive.start,
                        "end_offset": directive.end,
                        "offset_unit": "unicode_codepoint",
                        "start_line": directive.line,
                        "start_column": directive.column,
                        "end_line": directive.end_line,
                        "end_column": directive.end_column,
                    },
                },
            })
        return {"types": types, "facts": facts, "unresolved": unresolved}

    for i, token in enumerate(tokens):
        if token.value not in {"class", "interface", "struct", "enum", "record"}:
            continue
        name_index = i + 1
        if token.value == "record" and name_index < len(tokens) and tokens[name_index].value in {"class", "struct"}:
            name_index += 1
        if name_index >= len(tokens) or tokens[name_index].kind != "identifier":
            continue
        name = tokens[name_index].value.lstrip("@")
        arity = 0
        after_name = name_index + 1
        if after_name < len(tokens) and tokens[after_name].value == "<" and after_name in angle_pairs:
            generic_parts = _split_top(tokens, after_name + 1, angle_pairs[after_name])
            arity = len(generic_parts)
            after_name = angle_pairs[after_name] + 1
        namespace = _namespace_at(tokens, i, pairs)
        type_id = f"{namespace + '.' if namespace else ''}{name}`{arity}"
        declaration_end = after_name
        while declaration_end < len(tokens) and tokens[declaration_end].value not in ("{", ";"):
            declaration_end += 1
        if declaration_end >= len(tokens):
            continue
        is_record_struct = token.value == "record" and name_index == i + 2 and tokens[i + 1].value == "struct"
        is_class = token.value == "class" or (token.value == "record" and not is_record_struct)
        type_fact = {
            "id": _stable_id(["type", type_id, path, token.start]),
            "kind": "type_declaration",
            "type_id": type_id,
            "name": name,
            "namespace": namespace,
            "arity": arity,
            "declaration_kind": token.value,
            "source": _source_ref(path, source_hash, tokens, i, name_index + 1),
        }
        types.append(type_fact)
        facts.append(type_fact)
        if not is_class or declaration_end >= len(tokens) or tokens[declaration_end].value != "{":
            continue
        body_open = declaration_end
        body_close = pairs.get(body_open)
        if body_close is None:
            unresolved.append({"kind": "class_body", "reason": "unmatched class body", "source": type_fact["source"]})
            continue

        primary_params: list[dict[str, Any]] = []
        if after_name < len(tokens) and tokens[after_name].value == "(" and after_name in pairs:
            primary_params = _param_list(tokens, after_name + 1, pairs[after_name], pairs)
            for parameter in primary_params:
                param_start, param_end = parameter["start"], parameter["end"]
                facts.append({
                    "id": _stable_id(["injection", type_id, parameter["name"], path, tokens[param_start].start]),
                    "kind": "constructor_injection",
                    "owner_type_id": type_id,
                    "owner_namespace": namespace,
                    "parameter_name": parameter["name"],
                    "type_expression": parameter["type_expression"],
                    "source": _source_ref(path, source_hash, tokens, param_start, param_end),
                })

        class_header_start = _header_start(tokens, i, 0)
        class_attrs = _attributes(tokens, class_header_start, i, pairs)
        for attr in class_attrs:
            if attr["name"].split(".")[-1] == "Authorize":
                facts.append({
                    "id": _stable_id(["authorization_attribute", type_id, path, tokens[attr["start"]].start]),
                    "kind": "authorization_attribute",
                    "owner_type_id": type_id,
                    "attribute_name": attr["name"],
                    "source": _source_ref(path, source_hash, tokens, attr["start"], attr["end"]),
                })
        class_routes: list[tuple[str, dict[str, Any]]] = []
        class_route_problem = False
        for attr in class_attrs:
            if attr["name"].split(".")[-1] == "Route":
                if len(attr["arguments"]) == 1:
                    value, problem = _literal_arg(*attr["arguments"][0])
                    if problem:
                        class_route_problem = True
                        unresolved.append({"kind": "controller_route", "reason": problem, "source": _source_ref(path, source_hash, tokens, attr["start"], attr["end"])})
                    elif value is not None:
                        class_routes.append((value, attr))
                else:
                    class_route_problem = True
                    unresolved.append({"kind": "controller_route", "reason": "Route attribute is not one literal argument", "source": _source_ref(path, source_hash, tokens, attr["start"], attr["end"])})

        class_level = body_open + 1
        cursor = class_level
        while cursor < body_close:
            if tokens[cursor].value == "{" and cursor in pairs:
                cursor = pairs[cursor] + 1
                continue
            if tokens[cursor].value != "(" or cursor not in pairs or cursor == 0:
                cursor += 1
                continue
            close_paren = pairs[cursor]
            after_paren = close_paren + 1
            if after_paren >= body_close or tokens[after_paren].value not in ("{", "=>"):
                cursor += 1
                continue
            name_index = cursor - 1
            if tokens[name_index].kind != "identifier" or tokens[name_index].value in {"if", "for", "while", "switch", "catch", "using", "lock"}:
                cursor += 1
                continue
            method_name = tokens[name_index].value.lstrip("@")
            method_header_start = _header_start(tokens, name_index, class_level)
            method_params = _param_list(tokens, cursor + 1, close_paren, pairs)
            body_start = after_paren + 1 if tokens[after_paren].value == "{" else after_paren + 1
            if tokens[after_paren].value == "{":
                method_body_close = pairs.get(after_paren)
                if method_body_close is None:
                    unresolved.append({"kind": "method_body", "reason": "unmatched method body", "source": _source_ref(path, source_hash, tokens, name_index, close_paren + 1)})
                    cursor = close_paren + 1
                    continue
                body_end = method_body_close
                next_cursor = method_body_close + 1
            else:
                body_end = body_start
                while body_end < body_close and tokens[body_end].value != ";":
                    body_end += 1
                next_cursor = min(body_close, body_end + 1)
            method_id = _stable_id(["method", type_id, method_name, path, tokens[name_index].start])
            method_attrs = _attributes(tokens, method_header_start, name_index, pairs)
            facts.append({
                "id": method_id,
                "kind": "method_declaration",
                "owner_type_id": type_id,
                "method_name": method_name,
                "source": _source_ref(path, source_hash, tokens, method_header_start, body_end + 1 if tokens[after_paren].value == "{" else max(body_start + 1, body_end)),
            })
            for attr in method_attrs:
                if attr["name"].split(".")[-1] == "Authorize":
                    facts.append({
                        "id": _stable_id(["authorization_attribute", method_id, path, tokens[attr["start"]].start]),
                        "kind": "authorization_attribute",
                        "owner_type_id": type_id,
                        "method_id": method_id,
                        "attribute_name": attr["name"],
                        "source": _source_ref(path, source_hash, tokens, attr["start"], attr["end"]),
                    })
            http_attrs = [attr for attr in method_attrs if attr["name"].split(".")[-1] in {"HttpGet", "HttpPost", "HttpPut", "HttpDelete", "HttpPatch"}]
            for attr in http_attrs:
                if class_route_problem:
                    unresolved.append({"kind": "route_action", "reason": "action route suppressed because controller Route literal is unresolved", "source": _source_ref(path, source_hash, tokens, attr["start"], attr["end"])})
                    continue
                verb = attr["name"].split(".")[-1][4:].upper()
                if len(attr["arguments"]) == 0:
                    action_route = ""
                elif len(attr["arguments"]) == 1:
                    action_route, problem = _literal_arg(*attr["arguments"][0])
                    if problem:
                        unresolved.append({"kind": "route_action", "reason": problem, "source": _source_ref(path, source_hash, tokens, attr["start"], attr["end"])})
                        continue
                else:
                    unresolved.append({"kind": "route_action", "reason": "HTTP route attribute has multiple arguments", "source": _source_ref(path, source_hash, tokens, attr["start"], attr["end"])})
                    continue
                controller_route = class_routes[0][0] if len(class_routes) == 1 else None
                if len(class_routes) > 1:
                    unresolved.append({"kind": "route_action", "reason": "controller has multiple Route attributes; route composition is ambiguous", "source": _source_ref(path, source_hash, tokens, attr["start"], attr["end"])})
                    continue
                absolute_action_route = bool(action_route and (action_route.startswith("/") or action_route.startswith("~/")))
                if absolute_action_route:
                    action_route = action_route.removeprefix("~/").lstrip("/")
                full_route = "/".join(part.strip("/") for part in ((None if absolute_action_route else controller_route) or "", action_route or "") if part.strip("/"))
                facts.append({
                    "id": _stable_id(["route_action", method_id, verb, full_route]),
                    "kind": "route_action",
                    "action_id": method_id,
                    "controller_type_id": type_id,
                    "action_name": method_name,
                    "http_method": verb,
                    "controller_route_literal": None if absolute_action_route else controller_route,
                    "action_route_literal": action_route,
                    "route_literal": full_route,
                    "controller_route_source": (
                        _source_ref(path, source_hash, tokens, class_routes[0][1]["start"], class_routes[0][1]["end"])
                        if len(class_routes) == 1 and not absolute_action_route else None
                    ),
                    "source": _source_ref(path, source_hash, tokens, attr["start"], attr["end"]),
                })

            injectables = [fact for fact in facts if fact["kind"] == "constructor_injection" and fact["owner_type_id"] == type_id]
            for receiver in injectables:
                param_name = receiver["parameter_name"]
                shadowed = _method_shadowed(tokens, body_start, body_end, param_name, method_params)
                i = body_start
                while i + 2 < body_end:
                    if tokens[i].value != param_name or tokens[i + 1].value not in (".", "?.") or tokens[i + 2].kind != "identifier":
                        i += 1
                        continue
                    member_index = i + 2
                    call_open = member_index + 1
                    if call_open < body_end and tokens[call_open].value == "<" and call_open in angle_pairs:
                        call_open = angle_pairs[call_open] + 1
                    if call_open >= body_end or tokens[call_open].value != "(" or call_open not in pairs:
                        i += 1
                        continue
                    call_close = pairs[call_open]
                    syntax_fact = {
                        "id": _stable_id(["receiver_invocation_syntax", method_id, param_name, tokens[member_index].value, tokens[i].start]),
                        "kind": "receiver_invocation_syntax",
                        "owner_type_id": type_id,
                        "method_id": method_id,
                        "method_name": method_name,
                        "receiver_name": param_name,
                        "member_name": tokens[member_index].value,
                        "source": _source_ref(path, source_hash, tokens, i, call_close + 1),
                    }
                    facts.append(syntax_fact)
                    if shadowed:
                        unresolved.append({
                            "kind": "receiver_invocation_syntax",
                            "reason": "receiver name has a possible local or lambda shadow; parameter binding is unresolved",
                            "fact_id": syntax_fact["id"],
                            "receiver_name": param_name,
                            "member_name": tokens[member_index].value,
                            "source": syntax_fact["source"],
                        })
                    i = call_close + 1
            cursor = next_cursor

    for i, token in enumerate(tokens):
        if token.kind != "identifier" or token.value not in {
            "AddScoped", "AddTransient", "AddSingleton", "TryAddScoped", "TryAddTransient", "TryAddSingleton"
        }:
            continue
        generic_start = i + 1
        parsed = _generic_args(tokens, generic_start, angle_pairs)
        if parsed is None:
            continue
        args, generic_end = parsed
        call_open = generic_end + 1
        if call_open >= len(tokens) or tokens[call_open].value != "(":
            continue
        if len(args) != 2:
            unresolved.append({
                "kind": "dependency_registration",
                "reason": "registration does not have exactly two generic type arguments",
                "registration_method": token.value,
                "source": _source_ref(path, source_hash, tokens, i, call_open + 1),
            })
            continue
        service_expr = _type_text(tokens, args[0][0], args[0][1])
        implementation_expr = _type_text(tokens, args[1][0], args[1][1])
        aliased = [expr for expr in (service_expr, implementation_expr) if expr.split(".", 1)[0].lstrip("@") in aliases]
        facts.append({
            "id": _stable_id(["registration", token.value, service_expr, implementation_expr, path, token.start]),
            "kind": "dependency_registration",
            "registration_method": token.value,
            "service_type_expression": service_expr,
            "implementation_type_expression": implementation_expr,
            "namespace": _namespace_at(tokens, i, pairs),
            "source": _source_ref(path, source_hash, tokens, i, call_open + 1),
        })
        for expr in aliased:
            unresolved.append({
                "kind": "dependency_registration_type",
                "reason": "using alias encountered; target identity is not resolved by this extractor",
                "type_expression": expr,
                "fact_id": facts[-1]["id"],
                "source": facts[-1]["source"],
            })

    if unsupported_imports:
        unresolved.append({
            "kind": "using_directive",
            "reason": "namespace/import scope contains an unsupported alias, global/static, or namespace-scoped using directive",
            "source": {"path": path, "sha256": source_hash, "span": None},
        })
    return {"types": types, "facts": facts, "unresolved": unresolved, "imports": sorted(imports)}


_PRIMITIVES = {
    "bool": "System.Boolean", "byte": "System.Byte", "sbyte": "System.SByte",
    "short": "System.Int16", "ushort": "System.UInt16", "int": "System.Int32",
    "uint": "System.UInt32", "long": "System.Int64", "ulong": "System.UInt64",
    "float": "System.Single", "double": "System.Double", "decimal": "System.Decimal",
    "char": "System.Char", "string": "System.String", "object": "System.Object",
}


def build_graph(source_bytes: dict[str, bytes], inventory: dict[str, dict[str, Any]]) -> dict[str, Any]:
    parsed_files: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    source_files: list[dict[str, str]] = []
    for path in sorted(source_bytes, key=lambda value: value.encode("utf-8", "surrogatepass")):
        content = source_bytes[path]
        expected = inventory[path].get("sha256")
        actual = hashlib.sha256(content).hexdigest()
        if actual != expected:
            raise ValueError(f"source changed between inventory capture and graph extraction: {path!r}")
        source_files.append({"path": path, "sha256": actual})
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            unresolved.append({
                "kind": "source_file",
                "reason": "source is not UTF-8; extraction skipped",
                "source": {"path": path, "sha256": actual, "span": None},
            })
            continue
        parsed_files.append(_parse_file(path, text, actual))

    for path, entry in inventory.items():
        if path.lower().endswith(".cs") and path not in source_bytes:
            unresolved.append({
                "kind": "source_file",
                "reason": f"tracked C# source is not a regular readable file (presence={entry.get('presence')}, type={entry.get('type')})",
                "source": {"path": path, "sha256": entry.get("sha256"), "span": None},
            })

    facts = [fact for parsed in parsed_files for fact in parsed["facts"]]
    for fact in facts:
        fact["evidence_class"] = "observed_source_fact"
    unresolved.extend(item for parsed in parsed_files for item in parsed["unresolved"])
    type_facts = [fact for fact in facts if fact["kind"] == "type_declaration"]
    declarations_by_identity: dict[str, list[str]] = {}
    for fact in type_facts:
        declarations_by_identity.setdefault(fact["type_id"], []).append(fact["id"])

    candidates: list[dict[str, Any]] = []
    for fact in facts:
        expressions: list[tuple[str, str]] = []
        if fact["kind"] == "constructor_injection":
            expressions.append(("type_expression", fact["type_expression"]))
        elif fact["kind"] == "dependency_registration":
            expressions.extend((side, fact[side + "_type_expression"]) for side in ("service", "implementation"))
        if expressions:
            for side, expression in expressions:
                base_name = _candidate_base(expression)
                candidate_ids = [item["id"] for item in type_facts if item["name"] == base_name]
                candidate = {
                    "id": _stable_id(["name_candidate", fact["id"], side, expression, candidate_ids]),
                    "subject_fact_id": fact["id"],
                    "expression_side": side,
                    "type_expression": expression,
                    "candidate_fact_ids": candidate_ids,
                    "match_basis": "simple type-name match only",
                    "traversable": False,
                    "source": fact["source"],
                    "reason": "C# semantic binding is not performed; candidates are not resolved relationships",
                }
                candidates.append(candidate)
                unresolved.append({
                    "kind": "type_binding_candidate",
                    "reason": candidate["reason"],
                    "fact_id": fact["id"],
                    "candidate_id": candidate["id"],
                    "source": fact["source"],
                })
        elif fact["kind"] == "receiver_invocation_syntax":
            possible_injections = [
                item["id"] for item in facts
                if item["kind"] == "constructor_injection"
                and item["owner_type_id"] == fact["owner_type_id"]
                and item["parameter_name"] == fact["receiver_name"]
            ]
            candidate = {
                "id": _stable_id(["receiver_name_candidate", fact["id"], possible_injections]),
                "subject_fact_id": fact["id"],
                "expression_side": "receiver_name",
                "receiver_name": fact["receiver_name"],
                "candidate_fact_ids": possible_injections,
                "match_basis": "same owner and receiver spelling only",
                "traversable": False,
                "source": fact["source"],
                "reason": "receiver spelling does not establish parameter binding; local and lambda scopes are not resolved",
            }
            candidates.append(candidate)
            unresolved.append({
                "kind": "receiver_binding_candidate",
                "reason": candidate["reason"],
                "fact_id": fact["id"],
                "candidate_id": candidate["id"],
                "source": fact["source"],
            })

    links: list[dict[str, Any]] = []
    def link(kind: str, source_id: str, target_id: str, basis: str, evidence: list[str]) -> None:
        links.append({
            "id": _stable_id([kind, source_id, target_id, basis]),
            "kind": kind,
            "from_fact_id": source_id,
            "to_fact_id": target_id,
            "inferred": True,
            "resolution": "lexical_ownership",
            "basis": basis,
            "evidence_fact_ids": evidence,
        })

    injections = [fact for fact in facts if fact["kind"] == "constructor_injection"]
    for injection in injections:
        owner_declarations = declarations_by_identity.get(injection["owner_type_id"], [])
        if len(owner_declarations) == 1:
            link("type_has_injection", owner_declarations[0], injection["id"], "exact owner type identity", [owner_declarations[0], injection["id"]])
        elif len(owner_declarations) > 1:
            unresolved.append({"kind": "constructor_injection_owner", "reason": "owner type has multiple declarations", "fact_id": injection["id"], "candidates": owner_declarations, "source": injection["source"]})

    route_facts = [fact for fact in facts if fact["kind"] == "route_action"]
    invocation_facts = [fact for fact in facts if fact["kind"] == "receiver_invocation_syntax"]
    for invocation in invocation_facts:
        for route in route_facts:
            if route["action_id"] == invocation["method_id"]:
                link("route_action_contains_invocation", route["id"], invocation["id"], "same lexical method span contains receiver-name invocation syntax", [route["id"], invocation["id"]])

    # Multiple actions with one controller/name cannot be joined by name alone.
    action_groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for fact in route_facts:
        action_groups.setdefault((fact["controller_type_id"], fact["action_name"]), []).append(fact)
    for (controller_id, action_name), actions in action_groups.items():
        distinct = {action["action_id"] for action in actions}
        if len(distinct) > 1:
            for action in actions:
                unresolved.append({"kind": "route_action_overload", "reason": "overloaded action names are not joined by name", "type_id": controller_id, "action_name": action_name, "candidates": sorted(distinct), "fact_id": action["id"], "source": action["source"]})

    facts.sort(key=lambda fact: (fact["kind"], fact["source"]["path"], fact["source"]["span"]["start_offset"], fact["id"]))
    links.sort(key=lambda item: (item["kind"], item["from_fact_id"], item["to_fact_id"]))
    unresolved.sort(key=lambda item: (item.get("kind", ""), item.get("source", {}).get("path", ""), (item.get("source", {}).get("span") or {}).get("start_offset", -1), item.get("reason", "")))
    return {
        "extraction_method": EXTRACTION_METHOD,
        "extractor_identity": f"{EXTRACTION_METHOD}:python-stdlib-lexer",
        "facts_semantics": "Observed syntax with exact source hash and span.",
        "links_semantics": "Only lexical ownership and same-method syntax containment; no receiver-to-parameter or cross-file type binding.",
        "supported_forms": SUPPORTED_FORMS,
        "limitations": LIMITATIONS,
        "source_files": source_files,
        "facts": facts,
        "links": links,
        "candidates": candidates,
        "unresolved": unresolved,
    }
