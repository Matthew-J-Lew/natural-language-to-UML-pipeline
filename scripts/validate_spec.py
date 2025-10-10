#!/usr/bin/env python3
"""
validate_spec.py

Deterministically validates a single-bundle JSON spec against:
- required top-level keys,
- allowed devices/attributes/values (from caps.json),
- state definitions (ids + invariant atoms),
- transitions (sources/targets exist, trigger grammar, action grammar).

Exit codes:
  0 -> OK
  1 -> Validation errors printed to stdout (one per line)
  2 -> Wrong CLI usage
"""

import json
import re
import sys

# Collect all errors here and print them at the end (deterministic order).
ERRS: list[str] = []

# Regex for a single "atom" in a trigger/invariant:
#   <device>.<attribute> (==|!=) "<value>"
TRIG_ATOM_RE = re.compile(
    r'^\s*([a-zA-Z_]\w*)\.([a-zA-Z_]\w*)\s*(==|!=)\s*"([^"]+)"\s*$'
)

# Regex for an action:
#   <device>.<command>()
ACTION_RE = re.compile(
    r'^\s*([a-zA-Z_]\w*)\.([a-zA-Z_]\w*)\(\)\s*$'
)


def load(path: str):
    """Load JSON file with UTF-8 encoding."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def err(msg: str) -> None:
    """Record a validation error (no exceptions; we collect and report all)."""
    ERRS.append(msg)


def validate_devices(spec: dict, caps_root: dict):
    """
    Validate the devices array:
    - presence of 'devices' list,
    - each device has id/type/attributes,
    - type is known to caps.json,
    - attributes listed exist for that type,
    - required v1 devices exist: presenceSensor, motionSensor, switch.

    Returns:
        dev_map: { device_id -> device_type }
        caps_devices: shortcuts to caps_root['devices'] for convenience
    """
    if "devices" not in spec or not isinstance(spec["devices"], list):
        err("Missing devices[]")
        return {}, {}

    dev_map: dict[str, str] = {}
    caps_devices = caps_root.get("devices", {})

    for d in spec["devices"]:
        if not all(k in d for k in ("id", "type", "attributes")):
            err(f"Device missing keys: {d}")
            continue

        did = d["id"]
        dtype = d["type"]

        if dtype not in caps_devices:
            err(f"Unknown device type: {dtype}")
            continue

        if did in dev_map:
            err(f"Duplicate device id: {did}")

        dev_map[did] = dtype

        # Check that the attributes list is a subset of allowed attributes for this type.
        want_attrs = set(caps_devices[dtype]["attributes"].keys())
        got_attrs = set(d.get("attributes", []))
        if not got_attrs.issubset(want_attrs):
            invalid = sorted(got_attrs - want_attrs)
            err(f"Device {did} attributes invalid: {invalid}")

    # v1 pipeline requires exactly these devices to exist
    for must in ("presenceSensor", "motionSensor", "switch"):
        if must not in dev_map:
            err(f"Required device missing: {must}")

    return dev_map, caps_devices


def split_bool(expr: str, bool_ops: list[str]) -> list[str]:
    """
    Split an expression into tokens by boolean operators (&&, ||),
    preserving the operators as tokens and trimming whitespace on atoms.
    Example: 'a && b || c' -> ['a', '&&', 'b', '||', 'c']
    """
    tokens: list[str] = []
    buf = ""
    i = 0

    while i < len(expr):
        if expr.startswith("&&", i) or expr.startswith("||", i):
            tokens.append(buf.strip())
            tokens.append(expr[i:i + 2])
            buf = ""
            i += 2
        else:
            buf += expr[i]
            i += 1

    if buf.strip():
        tokens.append(buf.strip())

    return tokens


def validate_atom(atom: str, dev_map: dict, caps_devices: dict, ops: set[str]) -> None:
    """
    Validate a single atom against:
    - correct syntax via TRIG_ATOM_RE,
    - known device and attribute for that device type,
    - allowed operator (== or !=),
    - allowed value for attribute.
    """
    m = TRIG_ATOM_RE.match(atom)
    if not m:
        err(f"Bad trigger atom: {atom}")
        return

    dev, attr, op, val = m.groups()

    if dev not in dev_map:
        err(f"Unknown device in trigger: {dev}")
        return

    dtype = dev_map[dev]

    if attr not in caps_devices[dtype]["attributes"]:
        err(f"Unknown attribute {dev}.{attr}")
        return

    if op not in ops:
        err(f"Invalid operator {op} in {atom}")

    allowed_vals = set(caps_devices[dtype]["attributes"][attr])
    if val not in allowed_vals:
        err(f"Invalid value {val} for {dev}.{attr}; allowed={sorted(allowed_vals)}")


def validate_trigger(
    expr: str,
    dev_map: dict,
    caps_devices: dict,
    bool_ops: list[str],
    ops: set[str],
) -> None:
    """
    Validate an entire trigger expression (AND/OR of atoms).
    Pattern: atom ( (&&|||) atom )*
    """
    tokens = split_bool(expr, bool_ops)
    expect_atom = True

    for tok in tokens:
        if expect_atom:
            # We expect an atom next.
            validate_atom(tok, dev_map, caps_devices, ops)
            expect_atom = False
        else:
            # We expect a boolean operator next.
            if tok not in bool_ops:
                err(f"Expected boolean op between atoms, got: {tok}")
            expect_atom = True

    # Expression should not end with an operator.
    if tokens and expect_atom:
        err("Trigger expression ends with operator")


def validate_action(act: str, dev_map: dict, caps_devices: dict) -> None:
    """
    Validate an action: '<device>.<command>()', and ensure that:
    - device exists,
    - command is allowed for that device type (per caps.json).
    """
    m = ACTION_RE.match(act)
    if not m:
        err(f"Bad action syntax: {act}")
        return

    dev, cmd = m.groups()

    if dev not in dev_map:
        err(f"Unknown device in action: {dev}")
        return

    dtype = dev_map[dev]
    allowed = set(caps_devices[dtype]["actions"])
    if cmd not in allowed:
        err(
            f"Command {cmd} not allowed for {dev} (type {dtype}); "
            f"allowed={sorted(allowed)}"
        )


def main() -> None:
    # Basic CLI check
    if len(sys.argv) != 3:
        print("Usage: validate_spec.py <spec.json> <caps.json>", file=sys.stderr)
        sys.exit(2)

    spec_path = sys.argv[1]
    caps_path = sys.argv[2]

    # Load inputs
    spec = load(spec_path)
    caps_root = load(caps_path)

    # Operators from caps.json
    ops = set(caps_root.get("ops", []))
    bool_ops = caps_root.get("bool_ops", ["&&", "||"])

    # Check required top-level keys (contract)
    for k in ("bundle_name", "devices", "states", "transitions", "notes"):
        if k not in spec:
            err(f"Missing key: {k}")

    # Validate devices first; later checks depend on device types/attributes.
    dev_map, caps_devices = validate_devices(spec, caps_root)

    # Collect all state ids and validate state invariants (atoms only)
    state_ids: set[str] = set()
    states = spec.get("states")
    if isinstance(states, list):
        for st in states:
            if "id" not in st:
                err(f"State missing id: {st}")
                continue

            sid = st["id"]
            if sid in state_ids:
                err(f"Duplicate state id: {sid}")
            state_ids.add(sid)

            invs = st.get("invariants", [])
            if not isinstance(invs, list):
                err(f"State {sid} invariants must be list")
                continue

            for iv in invs:
                # State invariants are atoms (not OR/AND chains).
                m = TRIG_ATOM_RE.match(iv)
                if not m:
                    err(f"Bad invariant atom in state {sid}: {iv}")
                    continue

                dev, attr, op, val = m.groups()

                if dev not in dev_map:
                    err(f"Unknown device in invariant: {dev}")
                    continue

                dtype = dev_map[dev]
                if attr not in caps_devices[dtype]["attributes"]:
                    err(f"Unknown attribute {dev}.{attr} in invariant")

                if op not in ops:
                    err(f"Invalid operator {op} in invariant")

                if val not in caps_devices[dtype]["attributes"][attr]:
                    err(f"Invalid value {val} for {dev}.{attr} in invariant")

    # Validate transitions: existence of states + trigger/action grammar
    transitions = spec.get("transitions")
    if isinstance(transitions, list):
        for i, tr in enumerate(transitions, start=1):
            for k in ("source", "target", "trigger", "action"):
                if k not in tr:
                    err(f"Transition {i} missing {k}")

            src = tr.get("source")
            tgt = tr.get("target")

            if src not in state_ids:
                err(f"Transition {i} unknown source: {src}")
            if tgt not in state_ids:
                err(f"Transition {i} unknown target: {tgt}")

            validate_trigger(
                tr.get("trigger", ""),
                dev_map,
                caps_devices,
                bool_ops,
                ops,
            )
            validate_action(
                tr.get("action", ""),
                dev_map,
                caps_devices,
            )

    # Report results
    if ERRS:
        for e in ERRS:
            print(f"- {e}")
        sys.exit(1)

    print("OK")
    sys.exit(0)


if __name__ == "__main__":
    main()
