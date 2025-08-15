#!/usr/bin/env python3
# see notes at end. From chatGPT
import sys
import argparse

def reindent_lisp(lines, indent_width=4):
    depth = 0
    in_block_comment = 0  # supports nested #| |#
    in_string = False     # inside "..."
    in_bar = False        # inside |...| (escaped symbol)

    def count_prefix_closers(s):
        """Count leading ) chars (ignoring leading whitespace) that occur
        while not in string or block comment."""
        if in_block_comment or in_string or in_bar:
            return 0
        i = 0
        # skip leading whitespace
        while i < len(s) and s[i].isspace():
            i += 1
        c = 0
        while i < len(s) and s[i] == ')':
            c += 1
            i += 1
        return c

    def scan_line_for_delta(s):
        """Scan the line and return net paren depth change, updating no global state.
        Ignores anything after a ';' that occurs while not in string/bar/block-comment.
        Respects nested #| |#, strings, and |...|."""
        nonlocal in_block_comment, in_string, in_bar
        i = 0
        delta = 0
        while i < len(s):
            ch = s[i]

            # Handle block comments (#| ... |#), with nesting
            if not in_string and not in_bar:
                if in_block_comment:
                    # look for |#
                    if ch == '|' and i + 1 < len(s) and s[i+1] == '#':
                        in_block_comment -= 1
                        i += 2
                        continue
                    else:
                        i += 1
                        continue
                else:
                    # entering block comment?
                    if ch == '#' and i + 1 < len(s) and s[i+1] == '|':
                        in_block_comment += 1
                        i += 2
                        continue

            # If we hit a semicolon outside string/bar/block-comment, rest is a comment
            if not in_block_comment and not in_string and not in_bar and ch == ';':
                break

            # Toggle string on unescaped "
            if not in_block_comment and not in_bar and ch == '"':
                # count preceding backslashes to see if escaped
                bs = 0
                j = i - 1
                while j >= 0 and s[j] == '\\':
                    bs += 1
                    j -= 1
                if bs % 2 == 0:  # not escaped
                    in_string = not in_string
                i += 1
                continue

            # Toggle |...| bar-quoted symbol (not inside string or block comment)
            if not in_block_comment and not in_string and ch == '|':
                # In bar -> leave when next unescaped |
                if in_bar:
                    # count preceding backslashes to see if escaped
                    bs = 0
                    j = i - 1
                    while j >= 0 and s[j] == '\\':
                        bs += 1
                        j -= 1
                    if bs % 2 == 0:
                        in_bar = False
                else:
                    in_bar = True
                i += 1
                continue

            # Count parentheses only when not inside string/bar/block comment
            if not in_block_comment and not in_string and not in_bar:
                if ch == '(':
                    delta += 1
                elif ch == ')':
                    delta -= 1

            i += 1

        return delta

    out = []
    for raw in lines:
        line = raw.rstrip('\n')

        # Preserve completely blank lines verbatim
        if line.strip() == '':
            out.append('')
            continue

        # Compute indentation level based on current depth and leading closers
        closers_prefix = count_prefix_closers(line)
        indent_level = max(depth - closers_prefix, 0)

        # Strip existing leading whitespace and reapply indentation
        stripped = line.lstrip()
        new_line = (' ' * (indent_level * indent_width)) + stripped
        out.append(new_line)

        # Update depth after processing the line
        depth += scan_line_for_delta(line)
        # Do not allow negative depth in running count
        if depth < 0:
            depth = 0

    return '\n'.join(out) + ('\n' if lines and not lines[-1].endswith('\n') else '')

def main():
    ap = argparse.ArgumentParser(
        description="Re-indent Lisp code from stdin by parenthesis depth."
    )
    ap.add_argument(
        "-ind",
        type=int,
        default=4,
        help="spaces per indent level (default: 4)",
    )
    args = ap.parse_args()

    src = sys.stdin.read().splitlines(True)  # keep newlines
    sys.stdout.write(reindent_lisp(src, indent_width=args.ind))

if __name__ == "__main__":
    main()

#This is a pragmatic re-indenter (indent = paren depth). It doesn’t try to implement full Lisp style rules for special forms; it just lines code up correctly by structure.
#It preserves your original line breaks and only adjusts leading whitespace.
#Handles nested #| ... |# block comments, line comments, strings, and |...| symbols so that parentheses inside them don’t affect indentation.
