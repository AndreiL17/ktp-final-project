import json
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

import streamlit as st

KB_PATH = Path(__file__).parent / "kb.json"


def load_kb(path: Path = KB_PATH) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


# -------------------------
# Rules engine (unchanged)
# -------------------------

def rule_matches(conditions: Dict[str, Any], facts: Dict[str, Any]) -> bool:
    return all(facts.get(attr) == value for attr, value in conditions.items())


def score_rule(rule: Dict[str, Any]) -> Tuple[int, int]:
    """
    Scoring: (specificity, priority)
    - specificity: number of conditions (more conditions = more specific)
    - priority: optional tie-breaker (higher wins)
    """
    conditions = rule.get("conditions", {})
    specificity = len(conditions)
    priority = int(rule.get("priority", 0))
    return specificity, priority


def find_best_rule(kb: Dict[str, Any], facts: Dict[str, Any]) -> Dict[str, Any]:
    rules = kb.get("rules", [])
    best_rule: Optional[Dict[str, Any]] = None
    best_score = (-1, -1)

    for rule in rules:
        conditions = rule.get("conditions", {})
        if rule_matches(conditions, facts):
            s = score_rule(rule)
            if s > best_score:
                best_score = s
                best_rule = rule

    if best_rule is None:
        return kb.get("default", {"id": "default", "classification": "needs_review"})

    return best_rule


def show_decision(rule: Dict[str, Any], facts: Dict[str, Any]) -> None:
    classification = rule.get("classification", "needs_review")
    explanation = rule.get("explanation", "")
    steps = rule.get("recommended_next_steps", [])
    rule_id = rule.get("id", "unknown")

    st.subheader(f"Risk classification: {classification}")
    if explanation:
        st.write(explanation)

    st.caption(f"Rule applied: {rule_id}")

    if steps:
        st.markdown("### Recommended next steps")
        for step in steps:
            st.markdown(f"- {step}")

    with st.expander("Facts used for this decision"):
        st.json(facts)


# -------------------------
# Wizard UI (KB-driven)
# -------------------------

def init_state(attributes: Dict[str, Any]) -> None:
    if "step" not in st.session_state:
        st.session_state.step = 0
    if "facts" not in st.session_state:
        st.session_state.facts = {}
    if "last_result" not in st.session_state:
        st.session_state.last_result = None  # stores {"rule":..., "facts":...} after eval

    # Initialize keys with None so we can evaluate dependencies safely
    for attr_name in attributes.keys():
        st.session_state.facts.setdefault(attr_name, None)


def reset_wizard(attributes: Dict[str, Any]) -> None:
    st.session_state.step = 0
    st.session_state.facts = {k: None for k in attributes.keys()}
    st.session_state.last_result = None


def set_fact(attr_name: str, value: Any) -> None:
    st.session_state.facts[attr_name] = value


def get_fact(attr_name: str) -> Any:
    return st.session_state.facts.get(attr_name)


def _depends_on_satisfied(depends_on: Any, facts: Dict[str, Any]) -> bool:
    """
    Supports:
      - depends_on: {"some_key": true, "other_key": "internal"}
      - depends_on: [{"key":"x","equals":true}, ...]  (optional structure)
    If depends_on references keys not in facts, treat as NOT satisfied.
    """
    if not depends_on:
        return True

    if isinstance(depends_on, dict):
        for k, expected in depends_on.items():
            if k not in facts:
                return False
            if facts.get(k) != expected:
                return False
        return True

    if isinstance(depends_on, list):
        for cond in depends_on:
            if not isinstance(cond, dict):
                return False
            k = cond.get("key")
            expected = cond.get("equals")
            if not k or k not in facts:
                return False
            if facts.get(k) != expected:
                return False
        return True

    return False


def should_show(attr_name: str, attributes: Dict[str, Any]) -> bool:
    """
    Shows a question unless it has a 'depends_on' condition that isn't met.
    """
    attr_def = attributes.get(attr_name, {})
    depends_on = attr_def.get("depends_on")
    return _depends_on_satisfied(depends_on, st.session_state.facts)


def render_question(attr_name: str, attr_def: Dict[str, Any]) -> None:
    if not should_show(attr_name, st.session_state.attributes):
        # Clear hidden answers so rules don’t accidentally match stale values
        set_fact(attr_name, None)
        return

    q_type = attr_def.get("type", "text")
    question = attr_def.get("question", attr_name)

    current = get_fact(attr_name)

    if q_type == "bool":
        options = ["No", "Yes"]
        idx = 0 if current is None else (1 if current else 0)
        choice = st.radio(
            question,
            options,
            index=idx,
            horizontal=True,
            key=f"ui_{attr_name}_{st.session_state.step}",
        )
        set_fact(attr_name, choice == "Yes")

    elif q_type == "choice":
        options = attr_def.get("options", [])
        if not options:
            text_val = "" if current is None else str(current)
            val = st.text_input(
                question,
                value=text_val,
                key=f"ui_{attr_name}_{st.session_state.step}",
            )
            set_fact(attr_name, val if val != "" else None)
        else:
            idx = options.index(current) if current in options else 0
            val = st.selectbox(
                question,
                options,
                index=idx,
                key=f"ui_{attr_name}_{st.session_state.step}",
            )
            set_fact(attr_name, val)

    else:
        text_val = "" if current is None else str(current)
        val = st.text_input(
            question,
            value=text_val,
            key=f"ui_{attr_name}_{st.session_state.step}",
        )
        set_fact(attr_name, val if val != "" else None)


def build_pages_from_kb(attributes: Dict[str, Any], num_pages: int = 3) -> List[Dict[str, Any]]:
    """
    Prefer explicit paging if provided in kb.json:
      attribute: {"page": 1|2|3, ...}
    Otherwise, split attributes in their natural order into num_pages chunks.
    """
    names = list(attributes.keys())
    if not names:
        return [{"title": "Questions", "help": "", "fields": []}]

    has_page = any(isinstance(v, dict) and "page" in v for v in attributes.values())
    if has_page:
        buckets: Dict[int, List[str]] = {}
        for k, v in attributes.items():
            page = v.get("page")
            if isinstance(page, int):
                buckets.setdefault(page, []).append(k)
            else:
                buckets.setdefault(999, []).append(k)

        ordered_pages = sorted(buckets.keys())
        pages: List[Dict[str, Any]] = []
        titles = {1: "Data & audience", 2: "Controls & tooling", 3: "Domain & impact"}
        helps = {
            1: "Start with data types and where outputs will be seen.",
            2: "How the system is used and governed.",
            3: "What the system does and who it might affect.",
        }

        for p in ordered_pages:
            fields = buckets[p]
            if not fields:
                continue
            pages.append({
                "title": titles.get(p, f"Step {len(pages) + 1}"),
                "help": helps.get(p, ""),
                "fields": fields,
            })
        return pages

    chunk_size = max(1, (len(names) + num_pages - 1) // num_pages)
    chunks = [names[i:i + chunk_size] for i in range(0, len(names), chunk_size)]
    chunks = chunks[:num_pages]

    titles = ["Data & audience", "Controls & tooling", "Domain & impact"]
    helps = [
        "Start with data types and where outputs will be seen.",
        "How the system is used and governed.",
        "What the system does and who it might affect.",
    ]

    pages: List[Dict[str, Any]] = []
    for i, fields in enumerate(chunks):
        pages.append({
            "title": titles[i] if i < len(titles) else f"Step {i + 1}",
            "help": helps[i] if i < len(helps) else "",
            "fields": fields,
        })
    return pages


def facts_for_evaluation(attributes: Dict[str, Any]) -> Dict[str, Any]:
    """
    Keep only values that are currently visible (dependency satisfied) and non-empty.
    """
    out: Dict[str, Any] = {}
    for attr_name in attributes.keys():
        if should_show(attr_name, attributes):
            val = get_fact(attr_name)
            if val is not None and val != "":
                out[attr_name] = val
    return out


def wizard(attributes: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    init_state(attributes)
    st.session_state.attributes = attributes

    steps = build_pages_from_kb(attributes, num_pages=3)
    total_steps = len(steps)
    step_idx = max(0, min(st.session_state.step, total_steps - 1))
    is_last_step = (step_idx == total_steps - 1)

    # Progress + header
    st.progress((step_idx + 1) / total_steps)
    st.subheader(f"Step {step_idx + 1} of {total_steps}: {steps[step_idx]['title']}")
    if steps[step_idx]["help"]:
        st.caption(steps[step_idx]["help"])

    with st.form(key=f"step_form_{step_idx}"):
        for attr_name in steps[step_idx]["fields"]:
            attr_def = attributes.get(attr_name, {})
            render_question(attr_name, attr_def)

        # Navigation row
        # Next button should DISAPPEAR on last step, not just be disabled.
        if is_last_step:
            c1, c3 = st.columns([1, 2])
            with c1:
                back = st.form_submit_button("Back", disabled=(step_idx == 0))
            with c3:
                evaluate = st.form_submit_button("Evaluate use case", type="primary")
            next_btn = False
        else:
            c1, c2, c3 = st.columns([1, 1, 2])
            with c1:
                back = st.form_submit_button("Back", disabled=(step_idx == 0))
            with c2:
                next_btn = st.form_submit_button("Next")
            with c3:
                evaluate = False  # not shown until last step

    if back:
        st.session_state.step = max(0, step_idx - 1)
        st.rerun()

    if (not is_last_step) and next_btn:
        st.session_state.step = min(total_steps - 1, step_idx + 1)
        st.rerun()

    if is_last_step and evaluate:
        # Store result so reset button can remain visible after evaluation
        evaluated_facts = facts_for_evaluation(attributes)
        return evaluated_facts

    return None


# -------------------------
# App
# -------------------------

def app() -> None:
    st.set_page_config(page_title="GenAI Use Case Risk Advisor", layout="centered")

    # Slightly widen centered content column (optional, keep if you added it previously)
    st.markdown(
        """
        <style>
        .block-container {
            max-width: 900px;
            padding-left: 2rem;
            padding-right: 2rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.title("GenAI Use Case Risk Advisor")
    st.write("Answer a few short steps to receive a rule-based risk classification and recommended next steps.")

    kb = load_kb()
    attributes = kb.get("attributes", {})

    facts = wizard(attributes)

    # Always show Reset (even after evaluation)
    st.button("Reset", on_click=reset_wizard, args=(attributes,))

    if facts is not None:
        rule = find_best_rule(kb, facts)
        st.divider()
        show_decision(rule, facts)


if __name__ == "__main__":
    app()
