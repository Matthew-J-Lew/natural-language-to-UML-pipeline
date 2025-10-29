#!/usr/bin/env python3
import json, os, sys

def main():
    if len(sys.argv) != 3:
        print("Usage: gen_puml_from_spec.py <spec.json> <out_dir>", file=sys.stderr)
        sys.exit(2)

    spec_path, out_dir = sys.argv[1], sys.argv[2]
    with open(spec_path, "r", encoding="utf-8") as f:
        spec = json.load(f)

    bundle = spec.get("bundle_name", "Bundle1")
    states = spec.get("states", [])
    transitions = spec.get("transitions", [])
    devices = spec.get("devices", [])

    def esc(s: str) -> str:
        # Keep PlantUML text safe
        return s.replace("\r", "").replace("\n", "\\n")

    lines = []
    lines.append("@startuml")
    lines.append(f'title Bundle: {esc(bundle)} — State Machine Preview')
    lines += [
        "",
        "' --------- Visual polish ----------",
        "skinparam backgroundColor #FFFFFF",
        "skinparam state {",
        "  BorderColor #222222",
        "  BackgroundColor #FAFAFA",
        "  FontColor #111111",
        "}",
        "skinparam note {",
        "  BackgroundColor #FFFFEE",
        "  BorderColor #DDDD99",
        "}",
        "skinparam ArrowColor #333333",
        "skinparam ArrowFontColor #111111",
        "skinparam ArrowThickness 1.2",
        "hide empty description",
        "",
        "' --------- Legend ----------",
        "legend right",
        "  == Legend ==",
        "  - State note: invariants (must hold in state)",
        "  - Transition label: trigger / action",
        "  - Devices legend lists known devices, their types & attributes",
        "end legend",
        "",
        "' --------- Devices (legend, safe for all diagram types) ----------",
        "legend left",
        "  == Devices ==",
    ]

    for d in devices:
        did = d.get("id", "")
        dtype = d.get("type", "")
        attrs = ", ".join(d.get("attributes", []))
        lines.append(f"  {esc(did)} : {esc(dtype)}  (attrs: {esc(attrs)})")

    lines += [
        "end legend",
        "",
    ]

    # Initial node (state diagram)
    init_target = states[0]["id"] if states and states[0].get("id") else "State1"
    lines.append(f"[*] --> {esc(init_target)}")
    lines.append("")

    # States + invariants (note attached OUTSIDE the state)
    for s in states:
        sid = s.get("id", "")
        if not sid:
            continue
        # Declare state (no braces)
        lines.append(f'state "{esc(sid)}" as {esc(sid)}')
        invs = s.get("invariants", [])
        if invs:
            lines.append(f"note right of {esc(sid)}")
            lines.append("  == invariants ==")
            for iv in invs:
                lines.append(f"  {esc(iv)}")
            lines.append("end note")
    lines.append("")

    # Transitions
    for t in transitions:
        src = t.get("source", "")
        tgt = t.get("target", "")
        trig = t.get("trigger", "")
        act = t.get("action", "")
        if not src or not tgt:
            continue
        label = esc(trig) + (f" / {esc(act)}" if act else "")
        lines.append(f"{esc(src)} --> {esc(tgt)} : {label}")
    lines.append("")

    # Optional final node
    if len(states) > 1 and states[-1].get("id"):
        lines.append(f'{esc(states[-1]["id"])} --> [*]')

    lines.append("")
    lines.append("@enduml")

    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"Bundle_{bundle}.puml")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(out_path)

if __name__ == "__main__":
    main()
