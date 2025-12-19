#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# spectre_flatten_oop_legacy.py
#
# A practical Spectre netlist flattener designed for "EDA Python":
# - Works on Python 2.7+ and Python 3.x (no dataclasses, no typing, no __future__)
# - Spectre-correct hierarchy detection: inline if (master) matches a known subckt
# - Preserves top-level directives (include/options/save/simulator/global/...) as-is
# - Recursively inlines subckts and uniquifies internal nets with hierarchical prefixes
#
# Usage:
#   python spectre_flatten_oop_legacy.py input.scs
#   python spectre_flatten_oop_legacy.py input.scs output_flat.scs
#
# Notes:
# - This is not a full Spectre parser; it targets common netlisted structure.
# - It preserves parameter text but does not evaluate/substitute parameters.

import re
import sys
import io

SUBCKT_START_RE = re.compile(r'^\s*subckt\s+(\S+)\s*(.*)$', re.IGNORECASE)
SUBCKT_END_RE   = re.compile(r'^\s*ends\b', re.IGNORECASE)
GLOBAL_RE       = re.compile(r'^\s*global\b', re.IGNORECASE)

# NAME ( n1 n2 ... ) MASTER params...
PAREN_ELEM_RE   = re.compile(r'^\s*(\S+)\s*\(\s*([^)]*?)\s*\)\s*(.*)$')

DIRECTIVE_PREFIXES = (
    'simulator','options','save','include','ahdl_include','section',
    'parameters','paramset','statistics','assert','finalTimeOP'
)

COMMENT_PREFIXES = ('*','//')


class Element(object):
    def __init__(self, name, nodes, master, params, raw):
        self.name = name
        self.nodes = nodes
        self.master = master
        self.params = params
        self.raw = raw


class Subckt(object):
    def __init__(self, name, ports):
        self.name = name
        self.ports = ports
        self.elements = []


class SpectreNetlist(object):
    def __init__(self):
        self.subckts = {}     # name -> Subckt
        self.top_lines = []   # passthrough lines (directives/comments/blanks/unparsed)
        self.top_elems = []   # parsed elements at top level
        self.global_nodes = set(['0'])

    def join_continuations(self, lines):
        out = []
        buf = ''
        for raw in lines:
            line = raw.rstrip('\n')
            if buf:
                buf += ' ' + line.lstrip()
            else:
                buf = line
            if buf.rstrip().endswith('\\'):
                buf = buf.rstrip()[:-1].rstrip()
                continue
            out.append(buf)
            buf = ''
        if buf:
            out.append(buf)
        return out

    def is_blank_or_comment(self, line):
        s = line.strip()
        if not s:
            return True
        for p in COMMENT_PREFIXES:
            if s.startswith(p):
                return True
        return False

    def split_params(self, tokens):
        # Once we see '=' token, treat remainder as params.
        nonp, params = [], []
        seen = False
        for t in tokens:
            if (not seen) and ('=' in t):
                seen = True
            if seen:
                params.append(t)
            else:
                nonp.append(t)
        return nonp, params

    def parse_element(self, line):
        s = line.strip()
        if not s:
            return None

        m = PAREN_ELEM_RE.match(s)
        if m:
            name = m.group(1)
            nodes = m.group(2).split()
            rest = m.group(3).strip()
            if not rest:
                return None
            toks = rest.split()
            master = toks[0]
            params = ' '.join(toks[1:])
            return Element(name, nodes, master, params, line)

        # Fallback: NAME n1 n2 ... MASTER params...
        toks = s.split()
        if len(toks) < 3:
            return None
        name = toks[0]
        nonp, params = self.split_params(toks[1:])
        if len(nonp) < 2:
            return None
        nodes = nonp[:-1]
        master = nonp[-1]
        return Element(name, nodes, master, ' '.join(params), line)

    def parse(self, text, keep_directives=True):
        raw_lines = text.splitlines()
        lines = self.join_continuations(raw_lines)

        current = None  # Subckt or None

        for line in lines:
            if self.is_blank_or_comment(line):
                if current is None and keep_directives:
                    self.top_lines.append(line)
                continue

            if GLOBAL_RE.match(line):
                toks = line.split()
                for n in toks[1:]:
                    self.global_nodes.add(n)
                if current is None and keep_directives:
                    self.top_lines.append(line)
                continue

            sm = SUBCKT_START_RE.match(line)
            if sm:
                sub_name = sm.group(1)
                rest = sm.group(2).strip()
                ports = []
                for t in rest.split():
                    t2 = t.strip('()')
                    if not t2:
                        continue
                    if '=' in t2:
                        continue
                    ports.append(t2)
                current = Subckt(sub_name, ports)
                self.subckts[sub_name] = current
                continue

            if SUBCKT_END_RE.match(line):
                current = None
                continue

            # top-level directives pass-through (optional)
            head = line.strip().split()[0].lower()
            if (current is None) and any(head.startswith(p) for p in DIRECTIVE_PREFIXES):
                if keep_directives:
                    self.top_lines.append(line)
                continue

            elem = self.parse_element(line)
            if elem:
                if current is not None:
                    current.elements.append(elem)
                else:
                    self.top_elems.append(elem)
                continue

            if current is None and keep_directives:
                self.top_lines.append(line)

    @staticmethod
    def is_global(net, global_nodes):
        # Keep 0, any declared globals, and any net ending in !
        if net == '0':
            return True
        if net.endswith('!'):
            return True
        return net in global_nodes


class SpectreFlattener(object):
    def __init__(self, netlist, sep='.'):
        self.nl = netlist
        self.sep = sep
        self.out = []

    def flatten(self):
        # Start with passthrough top-level lines (includes/options/global/etc.)
        self.out.extend(self.nl.top_lines)

        for e in self.nl.top_elems:
            self._flatten_elem(e, path='', node_map={})
        return self.out

    def _flatten_elem(self, elem, path, node_map):
        full_name = elem.name if not path else path + self.sep + elem.name
        mapped_nodes = [node_map.get(n, n) for n in elem.nodes]

        # Spectre-correct: inline if master matches a known subckt
        if elem.master in self.nl.subckts:
            sub = self.nl.subckts[elem.master]

            # map ports -> actual nets
            port_map = {}
            for i, p in enumerate(sub.ports):
                if i < len(mapped_nodes):
                    port_map[p] = mapped_nodes[i]

            # breadcrumb comment
            self.out.append('* flatten: %s %s' % (full_name, elem.master))

            for child in sub.elements:
                child_map = dict(port_map)

                # uniquify internal nets that appear on this child's pins
                for n in child.nodes:
                    if n in sub.ports:
                        continue
                    if SpectreNetlist.is_global(n, self.nl.global_nodes):
                        continue
                    if n not in child_map:
                        child_map[n] = full_name + self.sep + n

                self._flatten_elem(child, path=full_name, node_map=child_map)
            return

        # leaf element: emit in paren form for consistency
        line = '%s (%s) %s' % (full_name, ' '.join(mapped_nodes), elem.master)
        if elem.params:
            line += ' ' + elem.params
        self.out.append(line)


def read_text(path):
    # Python2/3 friendly text read
    try:
        with io.open(path, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()
    except TypeError:
        # Python2 io.open doesn't have errors= in some builds; fallback
        with io.open(path, 'r', encoding='utf-8') as f:
            return f.read()

def write_text(path, text):
    try:
        with io.open(path, 'w', encoding='utf-8') as f:
            f.write(text)
    except TypeError:
        with io.open(path, 'w') as f:
            if isinstance(text, unicode):  # noqa: F821 (python2)
                f.write(text)
            else:
                f.write(text)

def main(argv):
    if len(argv) < 2:
        sys.stderr.write('Usage: spectre_flatten_oop_legacy.py input.scs [output.scs]\n')
        return 2

    in_path = argv[1]
    out_path = argv[2] if len(argv) > 2 else None
    if out_path is None:
        # default output name: <stem>_flat.scs
        if in_path.lower().endswith('.scs'):
            out_path = in_path[:-4] + '_flat.scs'
        else:
            out_path = in_path + '_flat'

    text = read_text(in_path)
    nl = SpectreNetlist()
    nl.parse(text, keep_directives=True)

    fl = SpectreFlattener(nl, sep='.')
    out_lines = fl.flatten()
    write_text(out_path, '\n'.join(out_lines) + '\n')

    sys.stdout.write('Wrote flattened netlist to: %s\n' % out_path)
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
