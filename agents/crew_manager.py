import os
from pydantic import BaseModel, Field
from typing import List, Optional
from crewai import Agent, Task, Crew, Process
from openai import AzureOpenAI, OpenAI
from langchain_openai import AzureChatOpenAI, ChatOpenAI

from helpers.openai_config import (
    resolve_azure_openai_api_key,
    resolve_azure_openai_api_version,
    resolve_azure_openai_endpoint,
    resolve_final_review_deployment_name,
    resolve_openai_base_url,
    resolve_scan_deployment_name,
)

class AzureChatOpenAIStopFix(AzureChatOpenAI):
    """
    Custom wrapper for AzureChatOpenAI to handle models that don't support 
    the 'stop' parameter (like o1-preview) or when the API version is strict.
    """
    def _generate(self, messages, stop=None, **kwargs):
        # Explicitly remove 'stop' to prevent 400 error on unsupported models
        return super()._generate(messages, stop=None, **kwargs)

    async def _agenerate(self, messages, stop=None, **kwargs):
        return await super()._agenerate(messages, stop=None, **kwargs)


class ChatOpenAIStopFix(ChatOpenAI):
    """
    Equivalent stop-stripping wrapper for OpenAI-compatible base_url routes.
    """

    def _generate(self, messages, stop=None, **kwargs):
        return super()._generate(messages, stop=None, **kwargs)

    async def _agenerate(self, messages, stop=None, **kwargs):
        return await super()._agenerate(messages, stop=None, **kwargs)

# --- Structured Data Models ---

class FinancialAnalysis(BaseModel):
    """The structured output from the Analyst to the Writer."""
    account_name: str = Field(..., description="The name of the nominal account")
    current_year: float = Field(..., description="Current year balance")
    prior_year: float = Field(..., description="Prior year balance")
    variance_abs: float = Field(..., description="Absolute variance")
    variance_pct: float = Field(..., description="Percentage variance")
    primary_drivers: List[str] = Field(..., description="List of material transactions or events driving the variance")
    key_counterparties: List[str] = Field(..., description="Top companies or individuals involved")
    risk_indicators: List[str] = Field(..., description="Any unusual patterns or potential misclassifications")

class AuditNote(BaseModel):
    """The final structured audit note."""
    content: str = Field(..., description="The final narrative synthesis paragraph")
    compliance_score: float = Field(..., description="Score from 0-1 on adherence to firm standards")
    math_verified: bool = Field(..., description="Whether the figures match the raw data")

# --- Agentic Framework ---

def resolve_token_param(deployment_name: str) -> str:
    """
    Pick the token-cap parameter name for the installed LangChain/OpenAI stack.

    The AI Foundry / OpenAI-compatible base_url route expects
    `max_completion_tokens` for GPT-5.4, while the older AzureChatOpenAI path
    in this repo has been more reliable with `max_tokens`. Keep an explicit env
    override for future upgrades.
    """
    override = os.environ.get("LLM_TOKEN_PARAM")
    if override:
        return override
    if resolve_openai_base_url():
        return "max_completion_tokens"
    return "max_tokens"


def build_llm(deployment_name: str):
    """
    Initialise Azure OpenAI LLM.
    We set temperature to 0.0 and use a fixed seed for maximum reproducibility.
    """
    # o1 models don't support temperature < 1.0 or seed currently
    is_o1 = "o1" in deployment_name.lower()
    
    # Use `max_tokens` by default because the current CrewAI/LangChain/OpenAI
    # stack raises `unexpected keyword argument 'max_completion_tokens'` in the
    # live review-note path even for GPT-5.4. Leave an env override for future
    # SDK/API combinations.
    token_param = resolve_token_param(deployment_name)

    timeout = float(os.environ.get("LLM_TIMEOUT_SECONDS", "60"))
    retries = int(os.environ.get("LLM_MAX_RETRIES", "2"))
    max_tokens = int(os.environ.get("LLM_MAX_TOKENS", "800"))
    base_url = resolve_openai_base_url()

    if base_url:
        config = {
            "base_url": base_url.rstrip("/") + "/",
            "api_key": resolve_azure_openai_api_key(),
            "model": deployment_name,
            "temperature": 1.0 if is_o1 else 0.0,
            "request_timeout": timeout,
            "max_retries": retries,
        }
        model_kwargs = {token_param: max_tokens}
        if not is_o1:
            model_kwargs["seed"] = 42
        config["model_kwargs"] = model_kwargs
        return ChatOpenAIStopFix(**config)

    config = {
        "azure_endpoint": resolve_azure_openai_endpoint(),
        "api_key": resolve_azure_openai_api_key(),
        "api_version": resolve_azure_openai_api_version(),
        "azure_deployment": deployment_name,
        "temperature": 1.0 if is_o1 else 0.0,
        "request_timeout": timeout,
        "max_retries": retries,
    }

    model_kwargs = {token_param: max_tokens}
    if not is_o1:
        model_kwargs["seed"] = 42
    config["model_kwargs"] = model_kwargs

    return AzureChatOpenAIStopFix(**config)

class ReviewCrew:
    def __init__(self):
        self.scan_deployment_name = resolve_scan_deployment_name()
        self.final_deployment_name = resolve_final_review_deployment_name()
        self.scan_llm = None
        self.final_llm = None

    def _get_scan_llm(self):
        if self.scan_llm is None:
            self.scan_llm = build_llm(self.scan_deployment_name)
        return self.scan_llm

    def _get_final_llm(self):
        if self.final_llm is None:
            self.final_llm = build_llm(self.final_deployment_name)
        return self.final_llm

    def senior_forensic_analyst(self) -> Agent:
        return Agent(
            role='Senior Forensic Accountant',
            goal='Extract precise financial variances and identify underlying economic drivers',
            backstory="""You are a specialist in UK GAAP and forensic audit. Your role is to look 
            past the numbers in the Trial Balance and identify the 'story' in the transactions. 
            You are meticulous about rounding and identifying material counterparties.""",
            llm=self._get_scan_llm(),
            verbose=True,
            allow_delegation=False,
            max_iter=15
        )

    def technical_accounting_writer(self) -> Agent:
        return Agent(
            role='Technical Accounting Specialist',
            goal='Transform analytical data into high-fidelity narrative review notes',
            backstory="""You specialise in technical financial reporting. You know how to 
            synthesise complex variance data into a single, punchy paragraph that 
            an Audit Partner would be proud to sign off. You adhere strictly to naming conventions.""",
            llm=self._get_scan_llm(),
            verbose=True,
            allow_delegation=False,
            max_iter=15
        )

    def audit_quality_partner(self) -> Agent:
        return Agent(
            role='Audit Quality Assurance Partner',
            goal='Perform a final cold review of the notes for compliance, grounding, and forbidden content',
            backstory="""You are the ultimate gatekeeper of quality. You have zero tolerance for 
            formatting errors, bullet points, or 'conversational' AI fluff. You ensure the note 
            is grounded strictly in the provided evidence and contains no forbidden identifiers.""",
            llm=self._get_final_llm(),
            verbose=True,
            allow_delegation=False,
            max_iter=15
        )

    def run_single_shot_review(self, account_name: str, briefing: str) -> str:
        """
        Produce a single-paragraph UK accountant review note in ONE LLM call.

        Much faster and more reliable than the 3-agent chain: the analyst /
        writer / reviewer split was prone to JSON-schema parsing failures, and
        when parsing failed the caller used to get the entire CrewAI internal
        log dump as the "review note".

        The briefing is expected to be the clean, human-readable per-account
        text produced by `helpers.xero_api_parser.fetch_and_format_xero_data`.
        """
        system_prompt = (
            "You are a UK chartered accountant "
            "preparing year-end review notes from Xero data. You write a single, "
            "factual paragraph per nominal account. You only use figures, "
            "vendor names and dates that appear in the briefing supplied; you "
            "never invent transactions, counterparties or amounts."
        )

        user_prompt = f"""\
Account under review: {account_name}

Briefing (figures, transactions, recurring items and anomalies pulled directly from Xero):
{briefing}

Write a SINGLE PARAGRAPH review note in this template:

  "<Current Year Figure £> vs <Prior Year Figure £> – £<variance> <increase|decrease> (<%>): \
<Current year description naming up to 3 real counterparties from the briefing> \
versus prior year <Prior year description naming up to 3 real counterparties> \
due to <plain-English economic reason inferred from the patterns>."

RULES (strictly enforced):
1. Use £ symbols and round to whole pounds.
2. Reference only counterparties, descriptions or amounts that are explicitly in the briefing.
3. If the variance is immaterial (under £500 absolute AND under 5%), state that plainly instead of inventing drivers.
4. If the briefing shows no transactions, comment on the closing balance only and say "no movement in the year".
5. Output ONE PARAGRAPH only. No bullet points, no headings, no journal numbers.
6. Do not add commentary about your own reasoning or the briefing format.
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            return self._invoke_direct_review_client(
                deployment_name=self.final_deployment_name,
                messages=messages,
            )
        except Exception as exc:
            if (
                "DeploymentNotFound" not in str(exc)
                or self.final_deployment_name == self.scan_deployment_name
            ):
                raise
            return self._invoke_direct_review_client(
                deployment_name=self.scan_deployment_name,
                messages=messages,
            )

    def _invoke_direct_review_client(self, deployment_name: str, messages: list[dict[str, str]]) -> str:
        """
        Use the plain OpenAI/AzureOpenAI clients for the production review-note
        path. This avoids LangChain parameter-mapping issues on the critical
        submission workflow while still leaving the richer CrewAI path available
        for experiments.
        """
        timeout = float(os.environ.get("LLM_TIMEOUT_SECONDS", "60"))
        is_o1 = "o1" in deployment_name.lower()

        kwargs = {
            "model": deployment_name,
            "messages": messages,
        }
        if not is_o1:
            kwargs["temperature"] = 0.0
            kwargs["seed"] = 42

        base_url = resolve_openai_base_url()
        if base_url:
            client = OpenAI(
                base_url=base_url.rstrip("/") + "/",
                api_key=resolve_azure_openai_api_key(),
                timeout=timeout,
                max_retries=int(os.environ.get("LLM_MAX_RETRIES", "2")),
            )
        else:
            client = AzureOpenAI(
                azure_endpoint=resolve_azure_openai_endpoint(),
                api_key=resolve_azure_openai_api_key(),
                api_version=resolve_azure_openai_api_version(),
                timeout=timeout,
                max_retries=int(os.environ.get("LLM_MAX_RETRIES", "2")),
            )

        response = client.chat.completions.create(**kwargs)

        text = response.choices[0].message.content or ""
        return text.strip()

    def run_synthesis(self, account_name: str, financial_context: str) -> str:
        # Agents
        analyst = self.senior_forensic_analyst()
        writer = self.technical_accounting_writer()
        reviewer = self.audit_quality_partner()

        # Task 1: Forensic Extraction
        extraction_task = Task(
            description=f"""Perform a forensic analysis of the following context for '{account_name}':
            {financial_context}
            
            Extract the exact figures for current vs prior year. 
            Identify the TOP 3 material transactions and the companies involved.
            Determine the economic reason for the variance (e.g. price hike, volume growth, timing).""",
            expected_output="A structured summary of the variance, drivers, and key counterparties.",
            agent=analyst,
            output_json=FinancialAnalysis
        )

        # Task 2: Narrative Synthesis
        synthesis_task = Task(
            description=f"""Using the structured analysis for {account_name}, write a professional review note.
            
            TEMPLATE:
            <Current Year Figure> vs <Last Year Figure> - <£variance> <increase/decrease> (<variance%>): <Current Year Breakdown> but last year, <Last Year Breakdown> to <Top Counterparties> because of <Economic Reason>.
            
            RULES:
            - Use GBP (£) symbols.
            - Ensure the tone is factual and professional.
            - DO NOT use bullet points.""",
            expected_output="A single-paragraph review note following the template above.",
            agent=writer,
            context=[extraction_task]
        )

        # Task 3: Compliance Audit
        audit_task = Task(
            description="""Perform a final Quality Control audit on the draft note.
            
            CHECKLIST:
            1. Is it a SINGLE paragraph? (Fail if multiple paragraphs)
            2. Are there ANY bullet points? (Fail if yes)
            3. Are there ANY journal numbers or transaction refs? (Fail if yes)
            4. Is it grounded in the analyst's data?
            
            REWRITE if any check fails. Final output must be ONLY the note text.""",
            expected_output="The final, audited, and compliant review note text.",
            agent=reviewer,
            context=[synthesis_task],
            output_json=AuditNote
        )

        # Execution
        crew = Crew(
            agents=[analyst, writer, reviewer],
            tasks=[extraction_task, synthesis_task, audit_task],
            process=Process.sequential,
            memory=False, # Disabled to prevent context bloat and iteration loops
            verbose=2
        )

        result = crew.kickoff()
        
        try:
            return result.json_dict['content'] if hasattr(result, 'json_dict') else str(result)
        except:
            return str(result)
