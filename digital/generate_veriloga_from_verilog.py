#!/usr/bin/env python3

"""
Generate simple behavioral Verilog-A models from structural gate-level Verilog.

Usage:

    python3 generate_veriloga_from_verilog.py /path/to/cells.v
    python3 generate_veriloga_from_verilog.py /path/to/cells.v cellname

Optional added ports:

    python3 generate_veriloga_from_verilog.py \
        /path/to/cells.v \
        --addports 'VDD,VDDS,VSS,SUBS'

    python3 generate_veriloga_from_verilog.py \
        /path/to/cells.v \
        cellname \
        --addports 'VDD:input,VDDS:input,VSS,SUBS'

Added ports default to inout. Explicit directions may be input, output, or
inout. Added ports are electrical interface ports only; they are not decoded
as Boolean logic inputs and do not create cross() events.

Supported Verilog primitives:

    and
    nand
    or
    nor
    xor
    xnor
    not
    buf

Assumptions and limitations:

  * Modules are combinational.
  * Modules may have one or more outputs.
  * Primitive instances use positional connections.
  * The first primitive terminal is the primitive output.
  * Remaining primitive terminals are primitive inputs.
  * Signals are scalar, not vectors.
  * Each generated signal has only one driver.
  * specify ... endspecify blocks are ignored.
  * Continuous assignments are not supported.
  * always blocks and other behavioral Verilog are not supported.
  * User-defined submodule instances are not flattened.
  * Primitive delay and drive-strength specifications are not supported.
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


@dataclass(frozen=True)
class AddedPort:
    name: str
    direction: str


@dataclass
class ExtractedModule:
    name: str
    port_header: str
    body: str


@dataclass
class Module:
    name: str
    ports: list[str]
    inputs: list[str]
    outputs: list[str]
    wires: list[str]
    gates: list[Gate]


def remove_comments(text: str) -> str:
    """Remove Verilog // and /* ... */ comments."""

    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
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


def find_matching_delimiter(
    text: str,
    opening_index: int,
    opening_char: str,
    closing_char: str,
) -> int:
    """Return the matching closing-delimiter index."""

    if opening_index >= len(text) or text[opening_index] != opening_char:
        raise ValueError(
            f"opening_index does not point to {opening_char!r}"
        )

    depth = 0

    for index in range(opening_index, len(text)):
        char = text[index]

        if char == opening_char:
            depth += 1
        elif char == closing_char:
            depth -= 1

            if depth == 0:
                return index

    raise ConversionError(f"Unmatched {opening_char!r} delimiter")


def find_matching_parenthesis(text: str, opening_index: int) -> int:
    """Return the ')' matching text[opening_index] == '('."""

    return find_matching_delimiter(text, opening_index, "(", ")")


def skip_whitespace(text: str, index: int) -> int:
    """Advance index past whitespace."""

    while index < len(text) and text[index].isspace():
        index += 1

    return index


def split_top_level_commas(text: str) -> list[str]:
    """Split at commas outside parentheses, brackets, and braces."""

    result: list[str] = []
    start = 0

    paren_depth = 0
    bracket_depth = 0
    brace_depth = 0

    for index, char in enumerate(text):
        if char == "(":
            paren_depth += 1
        elif char == ")":
            paren_depth -= 1
        elif char == "[":
            bracket_depth += 1
        elif char == "]":
            bracket_depth -= 1
        elif char == "{":
            brace_depth += 1
        elif char == "}":
            brace_depth -= 1
        elif (
            char == ","
            and paren_depth == 0
            and bracket_depth == 0
            and brace_depth == 0
        ):
            item = text[start:index].strip()

            if item:
                result.append(item)

            start = index + 1

    final_item = text[start:].strip()

    if final_item:
        result.append(final_item)

    return result


def split_statements(body: str) -> list[str]:
    """Split a module body into semicolon-terminated statements."""

    statements: list[str] = []
    start = 0

    paren_depth = 0
    bracket_depth = 0
    brace_depth = 0

    for index, char in enumerate(body):
        if char == "(":
            paren_depth += 1
        elif char == ")":
            paren_depth -= 1
        elif char == "[":
            bracket_depth += 1
        elif char == "]":
            bracket_depth -= 1
        elif char == "{":
            brace_depth += 1
        elif char == "}":
            brace_depth -= 1
        elif (
            char == ";"
            and paren_depth == 0
            and bracket_depth == 0
            and brace_depth == 0
        ):
            statement = body[start:index].strip()

            if statement:
                statements.append(statement)

            start = index + 1

    remainder = body[start:].strip()

    if remainder:
        raise ConversionError(
            "Unterminated or unsupported statement near "
            f"{remainder[:100]!r}"
        )

    return statements


def unique_preserving_order(items: Iterable[str]) -> list[str]:
    """Remove duplicates while preserving order."""

    seen: set[str] = set()
    result: list[str] = []

    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)

    return result


def validate_identifier(identifier: str, context: str) -> None:
    """Validate a simple scalar Verilog identifier."""

    if not IDENTIFIER_RE.fullmatch(identifier):
        raise ConversionError(
            f"Unsupported {context} {identifier!r}. "
            "Only simple scalar Verilog identifiers are supported."
        )


def parse_addports_spec(spec: str | None) -> list[AddedPort]:
    """
    Parse --addports.

    Examples:

        VDD,VDDS,VSS,SUBS
        VDD:input,VDDS:input,VSS,SUBS
    """

    if spec is None:
        return []

    spec = spec.strip()

    if not spec:
        raise ConversionError(
            "--addports was supplied with an empty port list"
        )

    added_ports: list[AddedPort] = []
    seen_names: set[str] = set()

    for raw_item in spec.split(","):
        item = raw_item.strip()

        if not item:
            raise ConversionError(
                "Empty item in --addports specification"
            )

        if ":" in item:
            parts = item.split(":")

            if len(parts) != 2:
                raise ConversionError(
                    f"Invalid --addports item {item!r}. "
                    "Expected PORT or PORT:DIRECTION."
                )

            port_name = parts[0].strip()
            direction = parts[1].strip().lower()
        else:
            port_name = item
            direction = "inout"

        validate_identifier(port_name, "--addports port name")

        if direction not in {"input", "output", "inout"}:
            raise ConversionError(
                f"Invalid direction {direction!r} for added port "
                f"{port_name!r}. Expected input, output, or inout."
            )

        if port_name in seen_names:
            raise ConversionError(
                f"Port {port_name!r} appears more than once in --addports"
            )

        seen_names.add(port_name)
        added_ports.append(
            AddedPort(name=port_name, direction=direction)
        )

    return added_ports


def extract_modules(source: str) -> list[ExtractedModule]:
    """
    Extract modules without validating their contents.

    Recognizes both:

        module name (...);
        module name;
    """

    modules: list[ExtractedModule] = []
    position = 0

    module_start_re = re.compile(
        r"\bmodule\s+([A-Za-z_][A-Za-z0-9_$]*)",
        flags=re.IGNORECASE,
    )

    endmodule_re = re.compile(
        r"\bendmodule\b",
        flags=re.IGNORECASE,
    )

    while True:
        module_match = module_start_re.search(source, position)

        if not module_match:
            break

        module_name = module_match.group(1)
        index = skip_whitespace(source, module_match.end())

        if index >= len(source):
            raise ConversionError(
                f"Module {module_name!r} has an incomplete declaration"
            )

        parameterized = False

        if source[index] == "#":
            parameterized = True
            index += 1
            index = skip_whitespace(source, index)

            if index >= len(source) or source[index] != "(":
                raise ConversionError(
                    f"Could not parse parameter list of module "
                    f"{module_name!r}"
                )

            parameter_end = find_matching_parenthesis(source, index)
            index = skip_whitespace(source, parameter_end + 1)

        if index < len(source) and source[index] == "(":
            port_end = find_matching_parenthesis(source, index)
            port_header = source[index + 1:port_end]
            semicolon_index = skip_whitespace(source, port_end + 1)

            if (
                semicolon_index >= len(source)
                or source[semicolon_index] != ";"
            ):
                raise ConversionError(
                    f"Expected ';' after port list of module "
                    f"{module_name!r}"
                )

        elif index < len(source) and source[index] == ";":
            port_header = ""
            semicolon_index = index

        else:
            semicolon_index = source.find(";", index)

            if semicolon_index < 0:
                raise ConversionError(
                    f"Could not find declaration terminator for module "
                    f"{module_name!r}"
                )

            port_header = ""

        end_match = endmodule_re.search(
            source,
            semicolon_index + 1,
        )

        if not end_match:
            raise ConversionError(
                f"No endmodule found for module {module_name!r}"
            )

        body = source[
            semicolon_index + 1:end_match.start()
        ]

        if parameterized:
            port_header = "__PARAMETERIZED_MODULE__" + port_header

        modules.append(
            ExtractedModule(
                name=module_name,
                port_header=port_header,
                body=body,
            )
        )

        position = end_match.end()

    return modules


def find_extracted_module(
    modules: list[ExtractedModule],
    requested_name: str,
) -> ExtractedModule | None:
    """Find a module by exact, case-sensitive name."""

    for module in modules:
        if module.name == requested_name:
            return module

    return None


def parse_declared_names(
    declaration: str,
    declaration_type: str,
) -> list[str]:
    """Parse names from an input/output/wire declaration."""

    declaration = declaration.strip()

    if "[" in declaration or "]" in declaration:
        raise ConversionError(
            f"Vector {declaration_type} declarations are not supported: "
            f"{declaration!r}"
        )

    declaration = re.sub(
        r"\b(?:wire|reg|logic|signed|unsigned|tri|wand|wor)\b",
        " ",
        declaration,
        flags=re.IGNORECASE,
    )

    names: list[str] = []

    for item in split_top_level_commas(declaration):
        item = item.strip()

        if "=" in item:
            raise ConversionError(
                f"Initialized {declaration_type} declaration is not "
                f"supported: {item!r}"
            )

        tokens = item.split()

        if len(tokens) != 1:
            raise ConversionError(
                f"Could not parse {declaration_type} declaration item "
                f"{item!r}"
            )

        name = tokens[0]
        validate_identifier(name, declaration_type)
        names.append(name)

    return names


def parse_ansi_port_header(
    port_header: str,
) -> tuple[list[str], list[str], list[str], bool]:
    """Attempt to parse an ANSI-style port header."""

    items = split_top_level_commas(port_header)

    if not items:
        return [], [], [], False

    ports: list[str] = []
    inputs: list[str] = []
    outputs: list[str] = []

    current_direction: str | None = None

    for item in items:
        direction_match = re.match(
            r"^(input|output|inout)\b(.*)$",
            item.strip(),
            flags=re.IGNORECASE | re.DOTALL,
        )

        if direction_match:
            current_direction = direction_match.group(1).lower()
            declaration = direction_match.group(2).strip()
        else:
            if current_direction is None:
                return [], [], [], False

            declaration = item.strip()

        if current_direction == "inout":
            raise ConversionError(
                "inout logic ports are not supported in the source module"
            )

        names = parse_declared_names(
            declaration,
            current_direction,
        )

        for name in names:
            ports.append(name)

            if current_direction == "input":
                inputs.append(name)
            elif current_direction == "output":
                outputs.append(name)

    return ports, inputs, outputs, True


def parse_non_ansi_port_header(port_header: str) -> list[str]:
    """Parse a traditional module port header."""

    ports: list[str] = []

    for item in split_top_level_commas(port_header):
        name = item.strip()
        validate_identifier(name, "port")
        ports.append(name)

    return ports


def parse_gate_statement(
    statement: str,
    generated_index: int,
) -> list[Gate]:
    """Parse one structural primitive statement."""

    primitive_match = re.match(
        r"^(and|nand|or|nor|xor|xnor|not|buf)\b(.*)$",
        statement,
        flags=re.IGNORECASE | re.DOTALL,
    )

    if not primitive_match:
        raise ConversionError(
            f"Unsupported primitive statement {statement[:100]!r}"
        )

    primitive = primitive_match.group(1).lower()
    remainder = primitive_match.group(2).strip()

    if remainder.startswith("#"):
        raise ConversionError(
            f"Primitive delay specification is not supported in "
            f"{statement[:100]!r}"
        )

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
                f"Could not parse {primitive} primitive instance "
                f"{chunk!r}"
            )

        instance_name = instance_match.group("name")

        if instance_name is None:
            instance_name = (
                f"unnamed_{primitive}_{generated_index}_{chunk_number}"
            )

        connections = [
            item.strip()
            for item in split_top_level_commas(
                instance_match.group("connections")
            )
        ]

        minimum_terminal_count = (
            2 if primitive in {"not", "buf"} else 3
        )

        if len(connections) < minimum_terminal_count:
            raise ConversionError(
                f"Primitive {primitive!r}, instance "
                f"{instance_name!r}, requires at least "
                f"{minimum_terminal_count} terminals"
            )

        for connection in connections:
            validate_identifier(
                connection,
                "primitive connection",
            )

        gate_output = connections[0]
        gate_inputs = connections[1:]

        if primitive in {"not", "buf"} and len(gate_inputs) != 1:
            raise ConversionError(
                f"Primitive {primitive!r}, instance "
                f"{instance_name!r}, must have exactly one input"
            )

        gates.append(
            Gate(
                primitive=primitive,
                instance=instance_name,
                output=gate_output,
                inputs=gate_inputs,
            )
        )

    return gates


def parse_module(extracted: ExtractedModule) -> Module:
    """Parse one extracted structural Verilog module."""

    module_name = extracted.name
    port_header = extracted.port_header
    body = extracted.body

    if port_header.startswith("__PARAMETERIZED_MODULE__"):
        raise ConversionError(
            "Parameterized module declarations are not supported"
        )

    if not port_header.strip():
        raise ConversionError(
            "Module has no ports and is not a convertible logic cell"
        )

    (
        ansi_ports,
        ansi_inputs,
        ansi_outputs,
        is_ansi,
    ) = parse_ansi_port_header(port_header)

    if is_ansi:
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

    for statement_index, statement in enumerate(
        statements,
        start=1,
    ):
        declaration_match = re.match(
            r"^(input|output|inout|wire|tri|wand|wor)\b(.*)$",
            statement,
            flags=re.IGNORECASE | re.DOTALL,
        )

        if declaration_match:
            declaration_type = declaration_match.group(1).lower()
            declaration_body = declaration_match.group(2)

            if declaration_type == "inout":
                raise ConversionError(
                    "inout logic ports are not supported in the source module"
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
                f"Could not identify statement "
                f"{statement[:100]!r}"
            )

        first_word = first_word_match.group(1).lower()

        if first_word not in SUPPORTED_PRIMITIVES:
            raise ConversionError(
                f"Unsupported statement beginning with "
                f"{first_word!r}: {statement[:100]!r}"
            )

        gates.extend(
            parse_gate_statement(
                statement,
                statement_index,
            )
        )

    inputs = unique_preserving_order(inputs)
    outputs = unique_preserving_order(outputs)
    wires = unique_preserving_order(wires)

    if not outputs:
        raise ConversionError("Module has no output ports")

    if not inputs:
        raise ConversionError("Module has no input ports")

    declared_ports = set(inputs) | set(outputs)

    missing_port_declarations = [
        port
        for port in ports
        if port not in declared_ports
    ]

    if missing_port_declarations:
        raise ConversionError(
            "Ports without input/output declarations: "
            + ", ".join(missing_port_declarations)
        )

    declarations_not_in_header = [
        signal
        for signal in inputs + outputs
        if signal not in ports
    ]

    if declarations_not_in_header:
        raise ConversionError(
            "Input/output declarations not present in the module "
            "port header: "
            + ", ".join(declarations_not_in_header)
        )

    duplicated_port_directions = set(inputs) & set(outputs)

    if duplicated_port_directions:
        raise ConversionError(
            "Signals declared as both input and output: "
            + ", ".join(sorted(duplicated_port_directions))
        )

    if not gates:
        raise ConversionError(
            "Module contains no supported primitive gates"
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
    """Topologically order primitive gates."""

    driver_by_signal: dict[str, Gate] = {}

    for gate in module.gates:
        if gate.output in driver_by_signal:
            previous_gate = driver_by_signal[gate.output]

            raise ConversionError(
                f"Signal {gate.output!r} has multiple drivers: "
                f"{previous_gate.instance!r} and "
                f"{gate.instance!r}"
            )

        if gate.output in module.inputs:
            raise ConversionError(
                f"Primitive {gate.instance!r} drives input port "
                f"{gate.output!r}"
            )

        driver_by_signal[gate.output] = gate

    for output_name in module.outputs:
        if output_name not in driver_by_signal:
            raise ConversionError(
                f"Output {output_name!r} is not driven by a "
                "supported primitive"
            )

    known_signals = set(module.inputs)
    remaining = list(module.gates)
    ordered: list[Gate] = []

    while remaining:
        made_progress = False
        unresolved: list[Gate] = []

        for gate in remaining:
            if all(
                input_signal in known_signals
                for input_signal in gate.inputs
            ):
                ordered.append(gate)
                known_signals.add(gate.output)
                made_progress = True
            else:
                unresolved.append(gate)

        if not made_progress:
            details: list[str] = []

            for gate in unresolved:
                unavailable_inputs = [
                    signal
                    for signal in gate.inputs
                    if signal not in known_signals
                ]

                details.append(
                    f"{gate.instance}: waiting for "
                    + ", ".join(unavailable_inputs)
                )

            raise ConversionError(
                "Could not resolve gate evaluation order. "
                "There may be an undriven signal or combinational loop:\n"
                "    "
                + "\n    ".join(details)
            )

        remaining = unresolved

    return ordered


def va_logic_name(signal_name: str) -> str:
    """Return the internal Verilog-A integer name."""

    return f"logic_{signal_name}"


def verilog_a_gate_expression(gate: Gate) -> str:
    """Generate a Verilog-A integer Boolean expression."""

    input_names = [
        va_logic_name(signal)
        for signal in gate.inputs
    ]

    if gate.primitive == "buf":
        return input_names[0]

    if gate.primitive == "not":
        return f"!({input_names[0]})"

    operator_by_primitive = {
        "and": "&&",
        "nand": "&&",
        "or": "||",
        "nor": "||",
        "xor": "^",
        "xnor": "^",
    }

    operator = operator_by_primitive[gate.primitive]

    joined_expression = (
        f" {operator} "
    ).join(
        f"({name})"
        for name in input_names
    )

    if gate.primitive in {"nand", "nor", "xnor"}:
        return f"!({joined_expression})"

    return joined_expression


def wrap_module_port_list(
    module_name: str,
    ports: list[str],
) -> list[str]:
    """Format the generated Verilog-A module port list."""

    lines = [f"module {module_name} ("]

    for index, port in enumerate(ports):
        comma = "," if index < len(ports) - 1 else ""
        lines.append(f"    {port}{comma}")

    lines.append(");")
    return lines


def get_effective_added_ports(
    module: Module,
    requested_added_ports: list[AddedPort],
) -> tuple[list[AddedPort], list[str]]:
    """Remove added ports already present in the source module."""

    existing_ports = set(module.ports)

    effective: list[AddedPort] = []
    already_present: list[str] = []

    for added_port in requested_added_ports:
        if added_port.name in existing_ports:
            already_present.append(added_port.name)
        else:
            effective.append(added_port)

    return effective, already_present


def generate_verilog_a(
    module: Module,
    added_ports: list[AddedPort] | None = None,
) -> str:
    """Generate complete Verilog-A source for one parsed module."""

    if added_ports is None:
        added_ports = []

    ordered_gates = order_gates(module)

    generated_signals = unique_preserving_order(
        gate.output
        for gate in ordered_gates
    )

    integer_logic_signals = unique_preserving_order(
        module.inputs + generated_signals
    )

    added_port_names = [
        port.name
        for port in added_ports
    ]

    all_ports = module.ports + added_port_names

    added_inputs = [
        port.name
        for port in added_ports
        if port.direction == "input"
    ]

    added_outputs = [
        port.name
        for port in added_ports
        if port.direction == "output"
    ]

    added_inouts = [
        port.name
        for port in added_ports
        if port.direction == "inout"
    ]

    lines: list[str] = []

    lines.append('`include "constants.vams"')
    lines.append('`include "disciplines.vams"')
    lines.append("")

    lines.extend(
        wrap_module_port_list(
            module.name,
            all_ports,
        )
    )

    lines.append("")

    if module.inputs:
        lines.append(
            f"    input  {', '.join(module.inputs)};"
        )

    if module.outputs:
        lines.append(
            f"    output {', '.join(module.outputs)};"
        )

    if added_inputs:
        lines.append(
            f"    input  {', '.join(added_inputs)};"
        )

    if added_outputs:
        lines.append(
            f"    output {', '.join(added_outputs)};"
        )

    if added_inouts:
        lines.append(
            f"    inout  {', '.join(added_inouts)};"
        )

    lines.append("")
    lines.append(
        f"    electrical {', '.join(all_ports)};"
    )
    lines.append("")

    lines.append(
        "    parameter real vlogic_high = 1.8;"
    )
    lines.append(
        "    parameter real vlogic_low  = 0.0;"
    )
    lines.append(
        "    parameter real vtrans      = "
        "(vlogic_high + vlogic_low) / 2.0;"
    )
    lines.append("")
    lines.append(
        "    parameter real tdel  = 1n from [0:inf);"
    )
    lines.append(
        "    parameter real trise = 1n from (0:inf);"
    )
    lines.append(
        "    parameter real tfall = 1n from (0:inf);"
    )
    lines.append("")
    lines.append(
        "    parameter real ttol     = 10p from (0:inf);"
    )
    lines.append(
        "    parameter real expr_tol = 10m from (0:inf);"
    )
    lines.append("")

    for signal in integer_logic_signals:
        lines.append(
            f"    integer {va_logic_name(signal)};"
        )

    lines.append("")
    lines.append("    analog begin")
    lines.append("        @(")
    lines.append("            initial_step")

    for input_name in module.inputs:
        lines.append(
            f"         or cross(V({input_name}) - vtrans, "
            "+1, ttol, expr_tol)"
        )
        lines.append(
            f"         or cross(V({input_name}) - vtrans, "
            "-1, ttol, expr_tol)"
        )

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
            f"            {va_logic_name(gate.output)} = "
            f"{expression};"
            f"  // {gate.primitive} {gate.instance}"
        )

    lines.append("        end")
    lines.append("")

    for output_index, output_name in enumerate(module.outputs):
        lines.append(
            f"        V({output_name}) <+ transition("
        )
        lines.append(
            f"            {va_logic_name(output_name)} "
            "? vlogic_high : vlogic_low,"
        )
        lines.append(
            "            tdel, trise, tfall"
        )
        lines.append("        );")

        if output_index < len(module.outputs) - 1:
            lines.append("")

    lines.append("    end")
    lines.append("")
    lines.append("endmodule")
    lines.append("")

    return "\n".join(lines)


def read_verilog_source(path: Path) -> str:
    """Read a Verilog file with an encoding fallback."""

    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            return path.read_text(encoding="latin-1")
        except OSError as error:
            raise ConversionError(
                f"Could not read {path}: {error}"
            ) from error
    except OSError as error:
        raise ConversionError(
            f"Could not read {path}: {error}"
        ) from error


def load_extracted_modules(path: Path) -> list[ExtractedModule]:
    """Read, clean, and extract all modules."""

    source = read_verilog_source(path)
    source = remove_comments(source)
    source = remove_specify_blocks(source)

    extracted_modules = extract_modules(source)

    if not extracted_modules:
        raise ConversionError(
            f"No module definitions found in {path}"
        )

    return extracted_modules


def parse_selected_modules(
    path: Path,
    requested_cell: str | None,
) -> tuple[list[Module], list[tuple[str, str]]]:
    """Parse one requested module or all convertible modules."""

    extracted_modules = load_extracted_modules(path)

    if requested_cell is not None:
        selected = find_extracted_module(
            extracted_modules,
            requested_cell,
        )

        if selected is None:
            available_names = ", ".join(
                module.name
                for module in extracted_modules
            )

            raise ConversionError(
                f"Module {requested_cell!r} was not found in {path}.\n"
                f"Available modules: {available_names}"
            )

        try:
            parsed = parse_module(selected)
        except ConversionError as error:
            raise ConversionError(
                f"While parsing requested module "
                f"{requested_cell!r}: {error}"
            ) from error

        return [parsed], []

    parsed_modules: list[Module] = []
    skipped_modules: list[tuple[str, str]] = []

    for extracted in extracted_modules:
        try:
            parsed_modules.append(
                parse_module(extracted)
            )
        except ConversionError as error:
            skipped_modules.append(
                (extracted.name, str(error))
            )

    return parsed_modules, skipped_modules


def write_output(
    module: Module,
    added_ports: list[AddedPort] | None = None,
) -> Path:
    """Generate and atomically write one <module>.va file."""

    output_path = Path.cwd() / f"{module.name}.va"
    temporary_path = Path.cwd() / f".{module.name}.va.tmp"

    content = generate_verilog_a(
        module,
        added_ports=added_ports,
    )

    try:
        temporary_path.write_text(
            content,
            encoding="utf-8",
        )

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
    """Construct the command-line parser."""

    parser = argparse.ArgumentParser(
        description=(
            "Generate electrical Verilog-A models from structural "
            "combinational gate-level Verilog modules."
        )
    )

    parser.add_argument(
        "verilog_file",
        type=Path,
        help=(
            "Input Verilog file containing structural module "
            "definitions"
        ),
    )

    parser.add_argument(
        "cellname",
        nargs="?",
        help=(
            "Optional module name to generate. If omitted, all "
            "convertible modules are generated."
        ),
    )

    parser.add_argument(
        "--addports",
        metavar="PORTS",
        help=(
            "Add electrical ports to every generated Verilog-A module. "
            "Syntax: 'VDD,VDDS,VSS,SUBS'. Added ports default to inout. "
            "Use PORT:input, PORT:output, or PORT:inout to specify a "
            "direction, for example "
            "'VDD:input,VDDS:input,VSS,SUBS'."
        ),
    )

    return parser


def main() -> int:
    """Program entry point."""

    parser = build_argument_parser()
    args = parser.parse_args()

    if not args.verilog_file.is_file():
        print(
            "ERROR: Input file does not exist or is not a regular "
            f"file: {args.verilog_file}",
            file=sys.stderr,
        )
        return 1

    try:
        requested_added_ports = parse_addports_spec(
            args.addports
        )

        modules_to_generate, skipped_modules = (
            parse_selected_modules(
                args.verilog_file,
                args.cellname,
            )
        )

    except ConversionError as error:
        print(
            f"ERROR: {error}",
            file=sys.stderr,
        )
        return 1

    generated_count = 0
    generation_failures = 0

    for module in modules_to_generate:
        effective_added_ports, already_present = (
            get_effective_added_ports(
                module,
                requested_added_ports,
            )
        )

        if already_present:
            print(
                f"WARNING: {module.name}: not adding ports already "
                f"present in the Verilog module: "
                f"{', '.join(already_present)}",
                file=sys.stderr,
            )

        try:
            output_path = write_output(
                module,
                added_ports=effective_added_ports,
            )

        except ConversionError as error:
            generation_failures += 1

            print(
                f"ERROR: Could not generate module "
                f"{module.name!r}: {error}",
                file=sys.stderr,
            )

            continue

        generated_count += 1

        output_word = (
            "output"
            if len(module.outputs) == 1
            else "outputs"
        )

        summary = (
            f"Generated: {output_path} "
            f"({len(module.outputs)} {output_word}"
        )

        if effective_added_ports:
            added_port_word = (
                "port"
                if len(effective_added_ports) == 1
                else "ports"
            )

            summary += (
                f", {len(effective_added_ports)} added "
                f"{added_port_word}"
            )

        summary += ")"
        print(summary)

    if skipped_modules:
        print(
            "\nSkipped modules:",
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
        f"generation failures {generation_failures}."
    )

    if args.cellname is not None:
        return 0 if generated_count == 1 else 1

    if generation_failures:
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
