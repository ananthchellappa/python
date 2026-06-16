# User Manual: `netlist_paths_topinst_v4.py`

## 1. Purpose

`netlist_paths_topinst_v4.py` reports hierarchical paths in a SPICE-style netlist.

It can search for either:

- instances of a target subckt/cell, using `--cell`
- instances with a specific instance name, using `--instname`

It can optionally restrict the search to:

- a top subckt/cell, using `--topcell`
- a top-level instance, using `--topinst`

It is intended for hierarchical netlists where subckt instances are represented by lines beginning with `X` or `x`.

---

## 2. Basic command form

```bash
python3 netlist_paths_topinst_v4.py [options] NETLIST_FILE
```

Example:

```bash
python3 netlist_paths_topinst_v4.py \
  --instpath \
  --topinst XDUT \
  --instname xMNcdio \
  LDR_4K_A0_chip_sim.sp
```

Example output:

```text
XDUT/XD_BOT_R/XBias_Ctrl/XLDR_4K_BOT_R_bias_1/XRampBias/xMNcdio
```

---

## 3. Required search target

You must specify exactly one of these:

```text
--cell CELL_NAME
--instname INSTANCE_NAME
```

They are mutually exclusive.

### 3.1 `--cell CELL_NAME`

Searches for instances whose instantiated subckt/cell is `CELL_NAME`.

Example:

```bash
python3 netlist_paths_topinst_v4.py \
  --topcell TOP \
  --cell BIAS_BLOCK \
  netlist.sp
```

This means:

```text
Starting at subckt TOP, find every instance that instantiates subckt BIAS_BLOCK.
```

### 3.2 `--instname INSTANCE_NAME`

Searches for instances whose instance name is `INSTANCE_NAME`.

Example:

```bash
python3 netlist_paths_topinst_v4.py \
  --topinst XDUT \
  --instname xMNcdio \
  --instpath \
  netlist.sp
```

This means:

```text
Starting under top-level instance XDUT, find every instance named xMNcdio.
```

`--instname` can find both hierarchical subckt instances and leaf-like X-instances such as primitive/PCell/model instances, as long as they appear on X-lines parsed by the script.

---

## 4. Optional search scope

You may specify zero or one of these:

```text
--topcell TOP_CELL_NAME
--topinst TOP_LEVEL_INSTANCE_NAME
```

They are mutually exclusive.

If neither is specified, the script searches from all discoverable roots in the netlist.

### 4.1 `--topcell TOP_CELL_NAME`

Starts traversal from a named subckt/cell.

Example:

```bash
python3 netlist_paths_topinst_v4.py \
  --topcell DUT_TOP \
  --instname xMNcdio \
  netlist.sp
```

This means:

```text
Look inside the subckt named DUT_TOP and find matching instance names.
```

`--topcell` expects a `.subckt` name, not an instance name.

### 4.2 `--topinst TOP_LEVEL_INSTANCE_NAME`

Starts traversal from a top-level instance outside any `.subckt`.

Example:

```bash
python3 netlist_paths_topinst_v4.py \
  --topinst XDUT \
  --instname xMNcdio \
  --instpath \
  netlist.sp
```

This means:

```text
Find the top-level instance named XDUT, enter the subckt that XDUT instantiates, then search below it.
```

`--topinst` expects the top-level instance name as written in the netlist.

For example, if the netlist contains:

```spice
XDUT net1 net2 net3 DUT_TOP
```

then the correct option is:

```bash
--topinst XDUT
```

not:

```bash
--topinst DUT_TOP
```

`DUT_TOP` is the instantiated cell/subckt name, not the top-level instance name.

---

## 5. Output modes

### 5.1 Default output

Without `--instpath`, output uses:

```text
root_cell/instance/instance/target
```

Example:

```text
DUT_TOP/XD_BOT_R/XBias_Ctrl/XRampBias/xMNcdio
```

The first element is a cell/subckt name. The remaining elements are instance names.

When default output is produced, the script also writes this note to stderr:

```text
Note: use --instpath to report pure instance-name paths.
```

### 5.2 `--instpath`

With `--instpath`, output uses only instance names.

Example:

```bash
python3 netlist_paths_topinst_v4.py \
  --instpath \
  --topinst XDUT \
  --instname xMNcdio \
  netlist.sp
```

Example output:

```text
XDUT/XD_BOT_R/XBias_Ctrl/XLDR_4K_BOT_R_bias_1/XRampBias/xMNcdio
```

This is usually the most useful mode when you want a path that can be copied as a pure hierarchical instance path.

---

## 6. `--dropx`

`--dropx` removes one leading `X` or `x` from each reported instance name.

Example raw output:

```text
XDUT/XD_BOT_R/XBias_Ctrl/xMNcdio
```

With `--dropx`:

```text
DUT/D_BOT_R/Bias_Ctrl/MNcdio
```

`--dropx` also affects matching for `--instname` and `--topinst`.

For example, if the raw instance is:

```text
xMNcdio
```

then this can match it:

```bash
--instname MNcdio --dropx
```

Similarly, if the raw top-level instance is:

```text
XDUT
```

then this can match it:

```bash
--topinst DUT --dropx
```

Without `--dropx`, `--topinst DUT` does not exactly match raw instance `XDUT`.

However, even without `--dropx`, the script prints closest-name suggestions when `--topinst` is not found.

---

## 7. Common examples

### 7.1 Find an instance name under a top-level instance

```bash
python3 netlist_paths_topinst_v4.py \
  --instpath \
  --topinst XDUT \
  --instname xMNcdio \
  netlist.sp
```

Example output:

```text
XDUT/XD_BOT_R/XBias_Ctrl/XLDR_4K_BOT_R_bias_1/XRampBias/xMNcdio
```

### 7.2 Find an instance name under a top cell

```bash
python3 netlist_paths_topinst_v4.py \
  --instpath \
  --topcell DUT_TOP \
  --instname xMNcdio \
  netlist.sp
```

This searches the subckt named `DUT_TOP`.

### 7.3 Find all instances of a subckt/cell under a top-level instance

```bash
python3 netlist_paths_topinst_v4.py \
  --instpath \
  --topinst XDUT \
  --cell RampBias \
  netlist.sp
```

This finds instances whose instantiated child cell is `RampBias` under top-level instance `XDUT`.

### 7.4 Search by post-drop instance name

If the netlist contains:

```text
xMNcdio
```

then this command can match it:

```bash
python3 netlist_paths_topinst_v4.py \
  --instpath \
  --topinst XDUT \
  --instname MNcdio \
  --dropx \
  netlist.sp
```

Output will also be printed with leading `X`/`x` removed from each instance name.

### 7.5 Use no top constraint

```bash
python3 netlist_paths_topinst_v4.py \
  --instpath \
  --instname xMNcdio \
  netlist.sp
```

This searches across all discoverable root hierarchies.

---

## 8. Diagnostics and defensive behavior

### 8.1 Bad `--topcell`

If the requested top cell is not defined as a `.subckt`, the script exits with an error:

```text
Error: top cell "DUT" is not defined in the netlist
```

### 8.2 Bad `--topinst`

If the requested top-level instance is not found, the script exits with an error and prints the closest top-level instance names.

Example command:

```bash
python3 netlist_paths_topinst_v4.py \
  --instpath \
  --topinst DUT \
  --instname xMNcdio \
  netlist.sp
```

If the real top-level instance is `XDUT`, the diagnostic is:

```text
Error: top-level instance "DUT" was not found in the netlist
Closest top-level instance name(s):
  XDUT
```

This closest-name diagnostic does not require `--dropx`.

### 8.3 Bad `--instname`

If no paths are found for an instance name, the script exits with an error and prints the closest instance names anywhere in the parsed netlist.

Example:

```text
No matching paths found for instance name "xMNcdlo" under top-level instance "XDUT".
Closest instance name(s) anywhere in the parsed netlist:
  xMNcdio
  xMNcdio_dummy
  Xfoo
```

The closest instance-name diagnostic is intentionally global. It does not currently restrict suggestions to the selected `--topcell` or `--topinst` scope.

### 8.4 Bad `--cell`

If the requested target cell is not defined as a `.subckt`, the script prints a warning:

```text
Warning: target cell "SomeCell" is not defined as a .subckt in the netlist
```

It may then produce no matches.

### 8.5 No matches

If the script completes the search but finds no output paths, it exits nonzero and prints a message like:

```text
No matching paths found for instance name "xMNcdio" under top-level instance "XDUT".
```

or:

```text
No matching paths found for cell "RampBias" under top cell "DUT_TOP".
```

---

## 9. What the parser recognizes

The script recognizes:

- `.subckt NAME ...`
- `.ends`
- instance lines beginning with `X` or `x`
- continuation lines beginning with `+`
- full-line comments beginning with `*`
- `//` comments at the end of a line

It builds hierarchy only through X-lines whose instantiated child cell is a defined `.subckt` in the same parsed netlist.

For `--instname`, the script can still find leaf X-instances whose child is not a defined subckt, as long as they appear inside a traversable subckt hierarchy.

---

## 10. Important limitations

### 10.1 Only X-lines are parsed as instances

The script focuses on subckt-style `X...` instance lines.

It does not treat lines beginning with `M`, `R`, `C`, `V`, etc. as searchable instances.

### 10.2 Child-cell extraction is heuristic

For an X-line, the script scans tokens from the right and skips parameter-like tokens such as `name=value`. The first remaining token is assumed to be the instantiated child cell.

This works for many SPICE-style netlists, but unusual syntax can confuse it.

### 10.3 Primitive/PCell leaf instances are not traversed

If an X-line instantiates something that is not defined as a `.subckt`, the script may still find that instance by `--instname`, but it cannot descend below it.

### 10.4 Closest `--instname` suggestions are global

When `--instname` fails, closest instance suggestions are taken from the whole parsed netlist, not just the selected scope.

### 10.5 Closest `--topinst` suggestions are top-level only

When `--topinst` fails, closest suggestions are only from top-level instances that instantiate defined subckts.

---

## 11. Exit behavior

Typical exit behavior:

```text
0  matches found and printed
1  invalid top cell or top-level instance
2  search completed but no matching paths were found
```

Warnings and diagnostics are printed to stderr. Matching paths are printed to stdout.

---

## 12. Recommended usage pattern

For most debugging work, use:

```bash
python3 netlist_paths_topinst_v4.py \
  --instpath \
  --topinst XDUT \
  --instname xMNcdio \
  netlist.sp
```

If you prefer paths without leading `X`/`x` prefixes:

```bash
python3 netlist_paths_topinst_v4.py \
  --instpath \
  --dropx \
  --topinst XDUT \
  --instname xMNcdio \
  netlist.sp
```

If you are not sure about the exact top-level instance name, try the best guess. The script will suggest close top-level instance names if the exact name is not found.
