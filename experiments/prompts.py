from __future__ import annotations

import os
import random
from dataclasses import dataclass
from typing import List, Sequence, Tuple

from strings.assistant import INSTRUCTION as DEFAULT_INSTRUCTION


@dataclass(frozen=True)
class PromptTemplate:
    system_instruction: str
    preamble: str
    constraints: str


class PromptTemplates:
    @staticmethod
    def default_template() -> PromptTemplate:
        instruction = os.environ.get("EXPERIMENT_INSTRUCTION", DEFAULT_INSTRUCTION)
        preamble = "You will be given accounting context. Generate review notes as specified."
        constraints = (
            "Constraints:\n"
            "- Output must be a single paragraph.\n"
            "- Do not include journal entry numbers.\n"
            "- Do not include transaction ref numbers.\n"
            "- Do not list all transactions; include only material drivers.\n"
        )
        return PromptTemplate(system_instruction=instruction, preamble=preamble, constraints=constraints)

    @staticmethod
    def few_shot_template(shots: list[tuple[str, str, str]]):
        """
        shots: list of (example_id, context, output)
        """
        base = PromptTemplates.default_template()
        preamble = base.preamble + "\n\nFew-shot examples follow."
        example_blocks: list[str] = []
        for eid, ctx, out in shots:
            example_blocks.append(f"EXAMPLE_ID={eid}\nCONTEXT:\n{ctx}\nOUTPUT:\n{out}".strip())
        constraints = base.constraints + "\n\n" + "\n\n".join(example_blocks)
        return PromptTemplate(system_instruction=base.system_instruction, preamble=preamble, constraints=constraints)

    @staticmethod
    def optimised_candidates(seed_text: str, rng: random.Random, trials: int) -> list[PromptTemplate]:
        base = PromptTemplates.default_template()
        variants: list[PromptTemplate] = []
        # Simple candidate set: re-ordering + stronger wording + shorter instruction knob.
        for _ in range(trials):
            tighten = rng.choice([True, False])
            extra = (
                "Focus on explaining variance drivers and recurring payments (subscriptions) when present.\n"
                if rng.choice([True, False])
                else ""
            )
            constraints = base.constraints + ("\n- Be terse and factual.\n" if tighten else "") + extra
            preamble = rng.choice(
                [
                    base.preamble,
                    "Act as an expert UK accounting partner. Produce audit-ready review notes.",
                    "Generate accountant review notes grounded strictly in the provided context.",
                ]
            )
            variants.append(
                PromptTemplate(
                    system_instruction=base.system_instruction,
                    preamble=preamble,
                    constraints=constraints,
                )
            )
        return variants


def render_prompt(template: PromptTemplate, context_text: str) -> str:
    # We keep everything in a single user message for portability across providers.
    return (
        template.system_instruction.strip()
        + "\n\n"
        + template.preamble.strip()
        + "\n\n"
        + template.constraints.strip()
        + "\n\n"
        + "CONTEXT:\n"
        + context_text.strip()
        + "\n\n"
        + "OUTPUT:"
    )
