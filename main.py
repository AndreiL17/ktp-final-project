import json
from pathlib import Path
import streamlit as st


KB_PATH = Path(__file__).parent / "kb.json"


def load_kb(path: Path = KB_PATH):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def build_front(attributes):
    facts = {}

    with st.form(key="use_case_form"):
        for attr_name, attr_def in attributes.items():
            q_type = attr_def.get("type", "text")
            question = attr_def.get("question", attr_name)
            key = f"attr_{attr_name}"

            if q_type == "bool":
                choice = st.radio(question, ["No", "Yes"], key=key)
                facts[attr_name] = (choice == "Yes")

            elif q_type == "choice":
                options = attr_def.get("options", [])
                value = st.selectbox(question, options, key=key)
                facts[attr_name] = value

            else:
                value = st.text_input(question, key=key)
                facts[attr_name] = value

        submitted = st.form_submit_button("Evaluate use case")

    if not submitted:
        return None
    return facts


def app():
    st.title("GenAI Use Case Risk Advisor")

    kb = load_kb()
    attributes = kb.get("attributes", {})

    facts = build_front(attributes)

    if facts is not None:
        st.info("Inference engine not implemented yet!")
        st.write("Collected facts:")
        st.json(facts)


if __name__ == "__main__":
    app()
