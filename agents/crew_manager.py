import os
from pydantic import BaseModel, Field
from typing import List, Optional
from crewai import Agent, Task, Crew, Process
from langchain_openai import AzureChatOpenAI

# --- Structured Data Models for the Dissertation ---

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

def get_llm():
    """
    Initialise Azure OpenAI LLM.
    We set temperature to 0.0 and use a fixed seed for maximum reproducibility 
    in a dissertation context.
    """
    return AzureChatOpenAI(
        azure_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT"),
        api_key=os.environ.get("AZURE_OPENAI_API_KEY"),
        api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-15-preview"),
        azure_deployment=os.environ.get("DEPLOYED_MODEL_NAME", "gpt-4o"),
        temperature=0.0,
        model_kwargs={"seed": 42}  # Fixed seed for deterministic-ish output
    )

class PHMCrew:
    def __init__(self):
        self.llm = get_llm()

    def senior_forensic_analyst(self) -> Agent:
        return Agent(
            role='Senior Forensic Accountant',
            goal='Extract precise financial variances and identify underlying economic drivers',
            backstory="""You are a specialist in UK GAAP and forensic audit. Your role is to look 
            past the numbers in the Trial Balance and identify the 'story' in the transactions. 
            You are meticulous about rounding and identifying material counterparties.""",
            llm=self.llm,
            verbose=True
        )

    def technical_accounting_writer(self) -> Agent:
        return Agent(
            role='Technical Accounting Specialist',
            goal='Transform analytical data into high-fidelity narrative review notes',
            backstory="""You specialise in technical financial reporting. You know how to 
            synthesise complex variance data into a single, punchy paragraph that 
            an Audit Partner would be proud to sign off. You adhere strictly to naming conventions.""",
            llm=self.llm,
            verbose=True
        )

    def audit_quality_partner(self) -> Agent:
        return Agent(
            role='Audit Quality Assurance Partner',
            goal='Perform a final cold review of the notes for compliance, grounding, and forbidden content',
            backstory="""You are the ultimate gatekeeper of quality at PHM. You have zero tolerance for 
            formatting errors, bullet points, or 'conversational' AI fluff. You ensure the note 
            is grounded strictly in the provided evidence and contains no forbidden identifiers.""",
            llm=self.llm,
            verbose=True
        )

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
            expected_output="A single-paragraph review note following the PHM template.",
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
            memory=True, # Enable memory for cross-task grounding
            verbose=2
        )

        result = crew.kickoff()
        
        try:
            return result.json_dict['content'] if hasattr(result, 'json_dict') else str(result)
        except:
            return str(result)
