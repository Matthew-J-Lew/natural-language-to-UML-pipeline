#!/usr/bin/env python3
"""
gen_uml_from_spec.py

Fills a minimal .uml XMI template (with markers) using a validated JSON spec.

Template must contain:
  - StateMachine name placeholder: __BUNDLE_NAME__
  - State/transition insertion blocks inside the Region:
        <!-- BEGIN_STATE_NODES -->
        <!-- END_STATE_NODES -->
        <!-- BEGIN_TRANSITIONS -->
        <!-- END_TRANSITIONS -->
  - Stereotype block after the </uml:Model> (as in your Bundle1):
        <!-- BEGIN_MDSSED_STEREOTYPES -->
        <!-- END_MDSSED_STEREOTYPES -->

Deterministic ids:
  - States: s_<StateId>
  - Pseudostate (initial): init_1
  - Final state: final_1
  - Init transition: t_init (no stereotypes)
  - User transitions: t_1, t_2, ...
  - Stereotypes: stinv_k, trig_i, act_i
"""

import html
import json
import os
import sys
import re


def h(x: str) -> str:
    """XML-escape a string for element text or attribute usage."""
    return html.escape(x, quote=True)


# --- Normalization to match the example bundle vocabulary used by MDSSED's SMV translator ---
_NOTPRESENT_EQ  = re.compile(r'(presenceSensor\.presence\s*==\s*)"notpresent"')
_NOTPRESENT_NEQ = re.compile(r'(presenceSensor\.presence\s*!=\s*)"notpresent"')

def normalize_expr(expr: str) -> str:
    """
    Normalize tokens so the Verify->SMV generator recognizes them.
    We keep JSON strict ("notpresent") and only adapt when writing UML.
    """
    expr = _NOTPRESENT_EQ.sub(r'\1"not present"', expr)
    expr = _NOTPRESENT_NEQ.sub(r'\1"not present"', expr)
    return expr


def make_state_nodes(states, state_xmi_ids) -> list[str]:
    """
    Create the region's subvertex list:
      - initial pseudostate (init_1)
      - all user states (s_<id>)
      - final state (final_1)
    """
    out = []
    out.append('      <subvertex xmi:type="uml:Pseudostate" xmi:id="init_1"/>')
    for s in states:
        sid = s["id"]
        out.append(
            f'      <subvertex xmi:type="uml:State" '
            f'xmi:id="{state_xmi_ids[sid]}" name="{h(sid)}"/>'
        )
    out.append('      <subvertex xmi:type="uml:FinalState" xmi:id="final_1"/>')
    return out


def make_transitions(states, transitions, state_xmi_ids) -> list[str]:
    """
    Create transitions:
      - t_init: init_1 -> first state in spec['states']
      - t_1..t_N: user transitions mapped by source/target state ids
    """
    out = []

    # Initial transition to the first declared state (deterministic)
    first_sid = states[0]["id"]
    out.append(
        f'      <transition xmi:type="uml:Transition" '
        f'xmi:id="t_init" source="init_1" target="{state_xmi_ids[first_sid]}"/>'
    )

    # User transitions
    for i, tr in enumerate(transitions, start=1):
        tid = f"t_{i}"
        src = state_xmi_ids[tr["source"]]
        tgt = state_xmi_ids[tr["target"]]
        out.append(
            f'      <transition xmi:type="uml:Transition" '
            f'xmi:id="{tid}" source="{src}" target="{tgt}"/>'
        )
    return out


def make_stereotypes(states, transitions, state_xmi_ids) -> list[str]:
    """
    Emit MDSSED blocks using the nested element style your example uses:
      - <MDSSED:states ...><state>...</state>...</MDSSED:states>
      - <MDSSED:triggers ...><trigger>...</trigger></MDSSED:triggers>
      - <MDSSED:actions  ...><action>...</action></MDSSED:actions>
    (No stereotypes for t_init.)
    """
    out = []

    # States → MDSSED:states with multiple <state> children
    inv_counter = 1
    for s in states:
        sid = s["id"]
        base = state_xmi_ids[sid]
        out.append(
            f'  <MDSSED:states xmi:id="stinv_{inv_counter}" base_State="{base}">'
        )
        for iv in s.get("invariants", []):
            out.append(f'    <state>{h(normalize_expr(iv))}</state>')
        out.append('  </MDSSED:states>')
        inv_counter += 1

    # Transitions → pair of trigger + action (skip t_init)
    for i, tr in enumerate(transitions, start=1):
        tid = f"t_{i}"
        out.append(
            f'  <MDSSED:triggers xmi:id="trig_{i}" base_Transition="{tid}">'
        )
        out.append(f'    <trigger>{h(normalize_expr(tr["trigger"]))}</trigger>')
        out.append('  </MDSSED:triggers>')

        out.append(
            f'  <MDSSED:actions xmi:id="act_{i}" base_Transition="{tid}">'
        )
        out.append(f'    <action>{h(tr["action"])}</action>')
        out.append('  </MDSSED:actions>')

    return out


def main() -> None:
    if len(sys.argv) != 4:
        print(
            "Usage: gen_uml_from_spec.py <spec.json> <template.tpl> <out_dir>",
            file=sys.stderr,
        )
        sys.exit(2)

    spec_path, tpl_path, out_dir = sys.argv[1], sys.argv[2], sys.argv[3]

    with open(spec_path, "r", encoding="utf-8") as f:
        spec = json.load(f)
    with open(tpl_path, "r", encoding="utf-8") as f:
        tpl = f.read()

    bundle = spec["bundle_name"]
    states = spec["states"]
    transitions = spec["transitions"]

    # Deterministic XMI ids for states
    state_xmi_ids = {s["id"]: f's_{s["id"]}' for s in states}

    # Build sections
    state_xml = make_state_nodes(states, state_xmi_ids)
    trans_xml = make_transitions(states, transitions, state_xmi_ids)
    stereo_xml = make_stereotypes(states, transitions, state_xmi_ids)

    # Fill template
    out_xml = (
        tpl
        .replace("__BUNDLE_NAME__", f"Bundle_{h(bundle)}")
        .replace("<!-- BEGIN_STATE_NODES -->",
                 "<!-- BEGIN_STATE_NODES -->\n" + "\n".join(state_xml))
        .replace("<!-- BEGIN_TRANSITIONS -->",
                 "<!-- BEGIN_TRANSITIONS -->\n" + "\n".join(trans_xml))
        .replace("<!-- BEGIN_MDSSED_STEREOTYPES -->",
                 "<!-- BEGIN_MDSSED_STEREOTYPES -->\n" + "\n".join(stereo_xml))
    )

    # Write output
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"Bundle_{bundle}.uml")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(out_xml)

    print(out_path)


if __name__ == "__main__":
    main()
