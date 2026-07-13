#!/usr/bin/env python3

"""
Generate simple behavioral Verilog-A models from structural gate-level Verilog.

Usage:

    python3 generate_veriloga_from_verilog.py /path/to/verilog_file
    python3 generate_veriloga_from_verilog.py /path/to/verilog_file cellname

With no cellname, one <module_name>.va file is generated in the current
directory for every convertible module in the input Verilog file.

Supported Verilog primitives:

    and
    nand
    or
    nor
    xor
    xnor
    not
    buf

Assumptions:

  * Each module is combinational.
  * Each module has exactly one output.
  * Primitive instances use positional connections.
  * The first primitive terminal is the output.
  * Remaining primitive terminals are inputs.
  * Signals are scalar, not vectors.
  * Intermediate signals have one driver.
  * specify ... endspecify blocks are ignored.
  * Continuous assignments and behavioral always blocks are not supported.

Example input:

    module example (X, A1, A2, B);

        output X;
        input  A1, A2, B;

        wire a_int;

        or   io1  (a_int, A1, A2);
        nand ina1 (X, a_int, B);

        specify
            ...
        endspecify

    endmodule
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")
SUPPORTED_PRIMITIVES = {
    "and",
    "nand",
    "or",
    "nor",
    "xor",
    "xnor",
    "not",
    "buf",
}


class ConversionError(Exception):
    """Raised when a module cannot be safely converted."""


@dataclass
class Gate:
    primitive: str
    instance: str
    output: str
    inputs: list[str]


@dataclass
class Module:
    name: str
    ports: list[str]
    inputs: list[str]
    outputs: list[str]
    wires: list[str]
    gates: list[Gate]


def remove_comments(text: str) -> str:
    """Remove // and /* ... */ comments from Verilog source."""

    # Remove block comments first.
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)

    # Remove line comments.
    text = re.sub(r"//[^\n]*", "", text)

    return text


def remove_specify_blocks(text: str) -> str:
    """Remove specify ... endspecify blocks."""

    return re.sub(
        r"\bspecify\b.*?\bendspecify\b",
        "",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )


def find_matching_parenthesis(text: str, opening_index: int) -> int:
    """Return the index of the ')' matching text[opening_index] == '('."""

    if opening_index >= len(text) or text[opening_index] != "(":
        raise ValueError("opening_index does not point to '('")

    depth = 0

    for index in range(opening_index, len(text)):
        char = text[index]

        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1

            if depth == 0:
                return index

    raise ConversionError("Unmatched '(' in module declaration")


def split_top_level_commas(text: str) -> list[str]:
    """
    Split at commas that are not inside parentheses or brackets.
    """

    result: list[str] = []
    start = 0
    paren_depth = 0
    bracket_depth = 0

    for index, char in enumerate(text):
        if char == "(":
            paren_depth += 1
        elif char == ")":
            paren_depth -= 1
        elif char == "[":
            bracket_depth += 1
        elif char == "]":
            bracket_depth -= 1
        elif char == "," and paren_depth == 0 and bracket_depth == 0:
            result.append(text[start:index].strip())
            start = index + 1

    final_part = text[start:].strip()

    if final_part:
        result.append(final_part)

    return result


def split_statements(body: str) -> list[str]:
    """
    Split a module body into semicolon-terminated statements.

    Semicolons inside parentheses are ignored.
    """

    statements: list[str] = []
    start = 0
    paren_depth = 0

    for index, char in enumerate(body):
        if char == "(":
            paren_depth += 1
        elif char == ")":
            paren_depth -= 1
        elif char == ";" and paren_depth == 0:
            statement = body[start:index].strip()

            if statement:
                statements.append(statement)

            start = index + 1

    remainder = body[start:].strip()

    if remainder:
        raise ConversionError(
            f"Unterminated or unsupported statement near: {remainder[:80]!r}"
        )

    return statements


def unique_preserving_order(items: Iterable[str]) -> list[str]:
    """Return unique items while retaining their original order."""

    seen: set[str] = set()
    result: list[str] = []

    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)

    return result


def validate_identifier(identifier: str, context: str) -> None:
    """Reject escaped identifiers, bit selections, expressions, and vectors."""

    if not IDENTIFIER_RE.fullmatch(identifier):
        raise ConversionError(
            f"Unsupported {context} {identifier!r}. "
            "Only simple scalar Verilog identifiers are supported."
        )


def parse_declared_names(declaration: str, declaration_type: str) -> list[str]:
    """
    Parse names from a declaration after input/output/wire/inout.

    Examples:

        input A, B
        output reg X
        wire a_int
    """

    declaration = declaration.strip()

    if "[" in declaration or "]" in declaration:
        raise ConversionError(
            f"Vector {declaration_type} declarations are not supported: "
            f"{declaration!r}"
        )

    # Remove common scalar qualifiers.
    declaration = re.sub(
        r"\b(?:wire|reg|logic|signed|unsigned|tri|supply0|supply1)\b",
        " ",
        declaration,
        flags=re.IGNORECASE,
    )

    names: list[str] = []

    for item in split_top_level_commas(declaration):
        item = item.strip()

        # Reject initialization or other declaration expressions.
        if "=" in item:
            raise ConversionError(
                f"Initialized {declaration_type} declaration is not supported: "
                f"{item!r}"
            )

        tokens = item.split()

        if len(tokens) != 1:
            raise ConversionError(
                f"Could not parse {declaration_type} declaration item: {item!r}"
            )

        name = tokens[0]
        validate_identifier(name, declaration_type)
        names.append(name)

    return names


def parse_ansi_port_header(
    port_header: str,
) -> tuple[list[str], list[str], list[str]]:
    """
    Parse an ANSI-style module port header.

    Example:

        input A1, input A2, input B, output X

    Also handles direction inheritance:

        input A1, A2, B, output X
    """

    ports: list[str] = []
    inputs: list[str] = []
    outputs: list[str] = []

    current_direction: str | None = None

    for item in split_top_level_commas(port_header):
        item = item.strip()

        direction_match = re.match(
            r"^(input|output|inout)\b(.*)$",
            item,
            flags=re.IGNORECASE | re.DOTALL,
        )

        if direction_match:
            current_direction = direction_match.group(1).lower()
            declaration = direction_match.group(2).strip()
        else:
            declaration = item

        if current_direction is None:
            # Non-ANSI header; caller will parse declarations from body.
            return [], [], []

        names = parse_declared_names(declaration, current_direction)

        for name in names:
            ports.append(name)

            if current_direction == "input":
                inputs.append(name)
            elif current_direction == "output":
                outputs.append(name)
            else:
                raise ConversionError(
                    "inout logic ports are not supported by this generator"
                )

    return ports, inputs, outputs


def parse_non_ansi_port_header(port_header: str) -> list[str]:
    """Parse a traditional module header containing only port names."""

    ports: list[str] = []

    for item in split_top_level_commas(port_header):
        name = item.strip()
        validate_identifier(name, "port")
        ports.append(name)

    return ports


def extract_modules(source: str) -> list[tuple[str, str, str]]:
    """
    Extract module name, port header, and body.

    Supports both:

        module cell_name (A, B, X);
            ...
        endmodule

    and modules with no ports:

        module filler_cell;
            ...
        endmodule

    Returns tuples:

        (module_name, port_header, module_body)

    port_header is an empty string for a module with no port list.
    """

    modules: list[tuple[str, str, str]] = []
    position = 0

    module_start_re = re.compile(
        r"\bmodule\s+([A-Za-z_][A-Za-z0-9_$]*)",
        flags=re.IGNORECASE,
    )

    endmodule_re = re.compile(r"\bendmodule\b", flags=re.IGNORECASE)

    while True:
        match = module_start_re.search(source, position)

        if not match:
            break

        module_name = match.group(1)
        index = match.end()

        # Skip whitespace after the module name.
        while index < len(source) and source[index].isspace():
            index += 1

        if index >= len(source):
            raise ConversionError(
                f"Module {module_name!r} has an incomplete declaration"
            )

        if source[index] == "#":
            raise ConversionError(
                f"Parameterized module {module_name!r} is not supported"
            )

        if source[index] == "(":
            close_paren = find_matching_parenthesis(source, index)
            port_header = source[index + 1 : close_paren]
            semicolon_index = close_paren + 1

            while (
                semicolon_index < len(source)
                and source[semicolon_index].isspace()
            ):
                semicolon_index += 1

            if (
                semicolon_index >= len(source)
                or source[semicolon_index] != ";"
            ):
                raise ConversionError(
                    f"Expected ';' after port list of module "
                    f"{module_name!r}"
                )

        elif source[index] == ";":
            # Legal module declaration with no ports:
            #
            #     module eco1fillcp;
            #
            port_header = ""
            semicolon_index = index

        else:
            declaration_preview = source[index : index + 40].splitlines()[0]

            raise ConversionError(
                f"Could not parse declaration of module {module_name!r} "
                f"near {declaration_preview!r}"
            )

        end_match = endmodule_re.search(source, semicolon_index + 1)

        if not end_match:
            raise ConversionError(
                f"No endmodule found for module {module_name!r}"
            )

        body = source[semicolon_index + 1 : end_match.start()]

        modules.append(
            (
                module_name,
                port_header,
                body,
            )
        )

        position = end_match.end()

    return modules
    
def find_extracted_module(
    extracted_modules: list[tuple[str, str, str]],
    requested_name: str,
) -> tuple[str, str, str] | None:
    """
    Find one extracted module by exact, case-sensitive name.
    """

    for module_data in extracted_modules:
        module_name, _, _ = module_data

        if module_name == requested_name:
            return module_data

    return None

def strip_leading_gate_modifiers(text: str) -> str:
    """
    Reject primitive drive strength and delay specifications.

    They could be ignored, but rejecting them avoids silently misparsing
    complicated primitive syntax.
    """

    stripped = text.lstrip()

    if stripped.startswith("#"):
        raise ConversionError(
            "Primitive delay specifications such as '#(...)' are not supported"
        )

    # A leading parenthesized item before the instance name normally means
    # a primitive drive-strength declaration.
    if stripped.startswith("("):
        raise ConversionError(
            "Primitive drive-strength specifications are not supported"
        )

    return stripped


def parse_gate_statement(statement: str, generated_index: int) -> list[Gate]:
    """
    Parse one primitive statement.

    Examples:

        and g1 (n1, A, B)
        not g2 (X, n1)
        and g1(n1,A,B), g2(X,n1,C)
    """

    primitive_match = re.match(
        r"^(and|nand|or|nor|xor|xnor|not|buf)\b(.*)$",
        statement,
        flags=re.IGNORECASE | re.DOTALL,
    )

    if not primitive_match:
        raise ConversionError(
            f"Unsupported module statement: {statement[:100]!r}"
        )

    primitive = primitive_match.group(1).lower()
    remainder = strip_leading_gate_modifiers(primitive_match.group(2))

    instance_chunks = split_top_level_commas(remainder)
    gates: list[Gate] = []

    for chunk_number, chunk in enumerate(instance_chunks, start=1):
        chunk = chunk.strip()

        instance_match = re.fullmatch(
            r"(?:(?P<name>[A-Za-z_][A-Za-z0-9_$]*)\s*)?"
            r"\((?P<connections>.*)\)",
            chunk,
            flags=re.DOTALL,
        )

        if not instance_match:
            raise ConversionError(
                f"Could not parse {primitive} primitive instance: {chunk!r}"
            )

        instance_name = instance_match.group("name")

        if instance_name is None:
            instance_name = (
                f"unnamed_{primitive}_{generated_index}_{chunk_number}"
            )

        connections = [
            connection.strip()
            for connection in split_top_level_commas(
                instance_match.group("connections")
            )
        ]

        minimum_terminals = 2 if primitive in {"not", "buf"} else 3

        if len(connections) < minimum_terminals:
            raise ConversionError(
                f"Primitive {primitive!r}, instance {instance_name!r}, "
                f"requires at least {minimum_terminals} terminals"
            )

        for connection in connections:
            validate_identifier(connection, "primitive connection")

        output = connections[0]
        inputs = connections[1:]

        if primitive in {"not", "buf"} and len(inputs) != 1:
            raise ConversionError(
                f"Primitive {primitive!r}, instance {instance_name!r}, "
                "must have exactly one input"
            )

        gates.append(
            Gate(
                primitive=primitive,
                instance=instance_name,
                output=output,
                inputs=inputs,
            )
        )

    return gates


def parse_module(
    module_name: str,
    port_header: str,
    body: str,
) -> Module:
    """Parse one extracted module."""

    ansi_ports, ansi_inputs, ansi_outputs = parse_ansi_port_header(
        port_header
    )

    if ansi_ports:
        ports = ansi_ports
        inputs = list(ansi_inputs)
        outputs = list(ansi_outputs)
    else:
        ports = parse_non_ansi_port_header(port_header)
        inputs = []
        outputs = []

    wires: list[str] = []
    gates: list[Gate] = []

    statements = split_statements(body)

    for statement_index, statement in enumerate(statements, start=1):
        declaration_match = re.match(
            r"^(input|output|inout|wire|tri)\b(.*)$",
            statement,
            flags=re.IGNORECASE | re.DOTALL,
        )

        if declaration_match:
            declaration_type = declaration_match.group(1).lower()
            declaration_body = declaration_match.group(2)

            if declaration_type == "inout":
                raise ConversionError(
                    f"Module {module_name!r} contains an inout port. "
                    "Only input and output logic ports are supported."
                )

            names = parse_declared_names(
                declaration_body,
                declaration_type,
            )

            if declaration_type == "input":
                inputs.extend(names)
            elif declaration_type == "output":
                outputs.extend(names)
            else:
                wires.extend(names)

            continue

        first_word_match = re.match(
            r"^([A-Za-z_][A-Za-z0-9_$]*)\b",
            statement,
        )

        if not first_word_match:
            raise ConversionError(
                f"Could not identify statement: {statement[:100]!r}"
            )

        first_word = first_word_match.group(1).lower()

        if first_word not in SUPPORTED_PRIMITIVES:
            raise ConversionError(
                f"Unsupported statement beginning with {first_word!r}: "
                f"{statement[:100]!r}"
            )

        gates.extend(parse_gate_statement(statement, statement_index))

    inputs = unique_preserving_order(inputs)
    outputs = unique_preserving_order(outputs)
    wires = unique_preserving_order(wires)

    if len(outputs) != 1:
        raise ConversionError(
            f"Module {module_name!r} has {len(outputs)} outputs; "
            "exactly one output is required"
        )

    declared_ports = set(inputs) | set(outputs)

    missing_port_declarations = [
        port for port in ports if port not in declared_ports
    ]

    if missing_port_declarations:
        raise ConversionError(
            f"Module {module_name!r} has ports without input/output "
            f"declarations: {', '.join(missing_port_declarations)}"
        )

    undeclared_header_ports = [
        signal for signal in inputs + outputs if signal not in ports
    ]

    if undeclared_header_ports:
        raise ConversionError(
            f"Module {module_name!r} has input/output declarations not "
            f"present in its port header: "
            f"{', '.join(undeclared_header_ports)}"
        )

    if not gates:
        raise ConversionError(
            f"Module {module_name!r} contains no supported primitive gates"
        )

    return Module(
        name=module_name,
        ports=ports,
        inputs=inputs,
        outputs=outputs,
        wires=wires,
        gates=gates,
    )


def order_gates(module: Module) -> list[Gate]:
    """
    Topologically order gates according to signal dependencies.
    """

    driver_by_signal: dict[str, Gate] = {}

    for gate in module.gates:
        if gate.output in driver_by_signal:
            other = driver_by_signal[gate.output]

            raise ConversionError(
                f"Signal {gate.output!r} in module {module.name!r} has "
                f"multiple drivers: {other.instance!r} and "
                f"{gate.instance!r}"
            )

        if gate.output in module.inputs:
            raise ConversionError(
                f"Gate {gate.instance!r} drives input port "
                f"{gate.output!r} in module {module.name!r}"
            )

        driver_by_signal[gate.output] = gate

    output_name = module.outputs[0]

    if output_name not in driver_by_signal:
        raise ConversionError(
            f"Output {output_name!r} of module {module.name!r} "
            "is not driven by a supported primitive"
        )

    known_signals = set(module.inputs)
    remaining = list(module.gates)
    ordered: list[Gate] = []

    while remaining:
        made_progress = False
        next_remaining: list[Gate] = []

        for gate in remaining:
            unknown_inputs = [
                signal
                for signal in gate.inputs
                if signal not in known_signals
            ]

            if not unknown_inputs:
                ordered.append(gate)
                known_signals.add(gate.output)
                made_progress = True
            else:
                next_remaining.append(gate)

        if not made_progress:
            details = []

            for gate in next_remaining:
                unknown = [
                    signal
                    for signal in gate.inputs
                    if signal not in known_signals
                ]

                details.append(
                    f"{gate.instance}: waiting for {', '.join(unknown)}"
                )

            raise ConversionError(
                f"Could not resolve gate order in module {module.name!r}. "
                "There may be a combinational loop or an undriven signal.\n"
                "    " + "\n    ".join(details)
            )

        remaining = next_remaining

    return ordered


def va_logic_name(signal_name: str) -> str:
    """Return the internal integer variable name for a Verilog signal."""

    return f"logic_{signal_name}"


def verilog_a_gate_expression(gate: Gate) -> str:
    """Generate the integer Boolean expression for a primitive gate."""

    inputs = [va_logic_name(signal) for signal in gate.inputs]

    if gate.primitive == "buf":
        return inputs[0]

    if gate.primitive == "not":
        return f"!({inputs[0]})"

    operator_by_primitive = {
        "and": "&&",
        "nand": "&&",
        "or": "||",
        "nor": "||",
        "xor": "^",
        "xnor": "^",
    }

    operator = operator_by_primitive[gate.primitive]
    joined = f" {operator} ".join(f"({item})" for item in inputs)

    if gate.primitive in {"nand", "nor", "xnor"}:
        return f"!({joined})"

    return joined


def wrap_port_list(module_name: str, ports: list[str]) -> list[str]:
    """Format the Verilog-A module port list."""

    if not ports:
        return [f"module {module_name} ();"]

    lines = [f"module {module_name} ("]

    for index, port in enumerate(ports):
        comma = "," if index != len(ports) - 1 else ""
        lines.append(f"    {port}{comma}")

    lines.append(");")
    return lines


def generate_verilog_a(module: Module) -> str:
    """Generate the complete Verilog-A source for one module."""

    ordered_gates = order_gates(module)
    output_name = module.outputs[0]

    generated_signals = unique_preserving_order(
        gate.output for gate in ordered_gates
    )

    internal_logic_signals = unique_preserving_order(
        module.inputs + generated_signals
    )

    lines: list[str] = []

    lines.append("`include \"constants.vams\"")
    lines.append("`include \"disciplines.vams\"")
    lines.append("")
    lines.extend(wrap_port_list(module.name, module.ports))
    lines.append("")

    lines.append(f"    input  {', '.join(module.inputs)};")
    lines.append(f"    output {output_name};")
    lines.append("")

    lines.append(f"    electrical {', '.join(module.ports)};")
    lines.append("")

    lines.append("    parameter real vlogic_high = 1.8;")
    lines.append("    parameter real vlogic_low  = 0.0;")
    lines.append(
        "    parameter real vtrans      = "
        "(vlogic_high + vlogic_low) / 2.0;"
    )
    lines.append("")
    lines.append("    parameter real tdel  = 1n from [0:inf);")
    lines.append("    parameter real trise = 1n from (0:inf);")
    lines.append("    parameter real tfall = 1n from (0:inf);")
    lines.append("")
    lines.append("    parameter real ttol     = 10p from (0:inf);")
    lines.append("    parameter real expr_tol = 10m from (0:inf);")
    lines.append("")

    for signal in internal_logic_signals:
        lines.append(f"    integer {va_logic_name(signal)};")

    lines.append("")
    lines.append("    analog begin")

    event_terms = ["initial_step"]

    for input_name in module.inputs:
        event_terms.append(
            f"cross(V({input_name}) - vtrans, +1, ttol, expr_tol)"
        )
        event_terms.append(
            f"cross(V({input_name}) - vtrans, -1, ttol, expr_tol)"
        )

    lines.append("        @(")

    for index, event_term in enumerate(event_terms):
        prefix = "            " if index == 0 else "         or "
        lines.append(f"{prefix}{event_term}")

    lines.append("        ) begin")

    for input_name in module.inputs:
        lines.append(
            f"            {va_logic_name(input_name)} = "
            f"(V({input_name}) > vtrans);"
        )

    lines.append("")

    for gate in ordered_gates:
        expression = verilog_a_gate_expression(gate)
        lines.append(
            f"            {va_logic_name(gate.output)} = {expression};"
            f"  // {gate.primitive} {gate.instance}"
        )

    lines.append("        end")
    lines.append("")
    lines.append(
        f"        V({output_name}) <+ transition("
    )
    lines.append(
        f"            {va_logic_name(output_name)} "
        "? vlogic_high : vlogic_low,"
    )
    lines.append("            tdel, trise, tfall")
    lines.append("        );")
    lines.append("    end")
    lines.append("")
    lines.append("endmodule")
    lines.append("")

    return "\n".join(lines)


def parse_verilog_file(
    path: Path,
    requested_cell: str | None = None,
) -> tuple[list[Module], list[tuple[str, str]]]:
    """
    Read and parse modules from a Verilog file.

    When requested_cell is supplied, only that module is parsed. Unsupported
    or malformed unrelated modules do not prevent its generation.

    When requested_cell is omitted, all modules are attempted. Modules that
    cannot be converted are skipped and returned in the warning list.

    Returns:

        (
            successfully_parsed_modules,
            [(skipped_module_name, reason), ...],
        )
    """

    try:
        source = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        source = path.read_text(encoding="latin-1")
    except OSError as error:
        raise ConversionError(f"Could not read {path}: {error}") from error

    source = remove_comments(source)
    source = remove_specify_blocks(source)

    extracted = extract_modules(source)

    if not extracted:
        raise ConversionError(f"No module definitions found in {path}")

    if requested_cell is not None:
        selected = find_extracted_module(extracted, requested_cell)

        if selected is None:
            available = ", ".join(
                module_name
                for module_name, _, _ in extracted
            )

            raise ConversionError(
                f"Module {requested_cell!r} was not found in {path}.\n"
                f"Available modules: {available}"
            )

        module_name, port_header, body = selected

        try:
            module = parse_module(module_name, port_header, body)
        except ConversionError as error:
            raise ConversionError(
                f"While parsing requested module {module_name!r}: {error}"
            ) from error

        return [module], []

    parsed_modules: list[Module] = []
    skipped_modules: list[tuple[str, str]] = []

    for module_name, port_header, body in extracted:
        try:
            module = parse_module(module_name, port_header, body)
        except ConversionError as error:
            skipped_modules.append((module_name, str(error)))
            continue

        parsed_modules.append(module)

    return parsed_modules, skipped_modules

def write_output(module: Module) -> Path:
    """Generate and write one Verilog-A output file."""

    output_path = Path.cwd() / f"{module.name}.va"
    temporary_path = output_path.with_suffix(".va.tmp")

    content = generate_verilog_a(module)

    try:
        temporary_path.write_text(content, encoding="utf-8")
        temporary_path.replace(output_path)
    except OSError as error:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass

        raise ConversionError(
            f"Could not write {output_path}: {error}"
        ) from error

    return output_path


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate electrical Verilog-A models from structural "
            "gate-level Verilog modules."
        )
    )

    parser.add_argument(
        "verilog_file",
        type=Path,
        help="Input Verilog file containing structural module definitions",
    )

    parser.add_argument(
        "cellname",
        nargs="?",
        help=(
            "Optional module name to convert. If omitted, all convertible "
            "modules are generated."
        ),
    )

    return parser


def main() -> int:
    parser = build_argument_parser()
    args = parser.parse_args()

    if not args.verilog_file.is_file():
        print(
            f"ERROR: Input file does not exist or is not a regular file: "
            f"{args.verilog_file}",
            file=sys.stderr,
        )
        return 1

    try:
        modules_to_generate, skipped_modules = parse_verilog_file(
            args.verilog_file,
            requested_cell=args.cellname,
        )
    except ConversionError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    generated_count = 0
    failed_count = 0

    for module in modules_to_generate:
        try:
            output_path = write_output(module)
        except ConversionError as error:
            failed_count += 1

            print(
                f"ERROR: Could not generate module "
                f"{module.name!r}: {error}",
                file=sys.stderr,
            )

            continue

        generated_count += 1
        print(f"Generated: {output_path}")

    if skipped_modules:
        print(
            "\nSkipped modules that are not convertible:",
            file=sys.stderr,
        )

        for module_name, reason in skipped_modules:
            print(
                f"  WARNING: {module_name}: {reason}",
                file=sys.stderr,
            )

    print(
        f"\nGenerated {generated_count} module(s); "
        f"skipped {len(skipped_modules)} module(s); "
        f"generation failures {failed_count}."
    )

    if args.cellname is not None:
        return 0 if generated_count == 1 else 1

    # In all-cells mode, skipped unsupported cells are warnings rather than
    # a fatal error. Return failure only if no models could be generated or
    # an actual output-file generation failed.
    if failed_count:
        return 1

    if generated_count == 0:
        print(
            "ERROR: No convertible modules were found.",
            file=sys.stderr,
        )
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main())
