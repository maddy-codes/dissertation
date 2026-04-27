from strings.paths import FILE_PATH_OUT
from helpers.utility import save_systematic_output
from agents.crew_manager import PHMCrew
import os
import dotenv

dotenv.load_dotenv()

def run_all_crew(
    messages,
    mp_df,
    FILE_PATH_OUT=FILE_PATH_OUT,
    emit_event=None,
):
    """
    Dissertation-grade Multi-Agentic Execution using CrewAI.
    Bypasses the monolithic OpenAI Assistant.
    """
    all_responses = []
    
    # Initialise the PHM Multi-Agent Crew
    phm_crew = PHMCrew()

    for message in messages:
        account_name = message["name"]
        financial_context = message["message"]
        
        try:
            if emit_event:
                emit_event("account_start", account=account_name, message="Multi-agent synthesis in progress (Analyst -> Writer -> Reviewer)...")
            
            # Kickoff the agentic process
            response = phm_crew.run_synthesis(account_name, financial_context)
            
            # Clean response (CrewAI output is a special object in newer versions, ensure it's string)
            response_str = str(response).strip()
            
            mp_df.loc[mp_df["xero_names"] == account_name, "ai_summary"] = response_str
            all_responses.append(response_str)
            
            if emit_event:
                emit_event("account_complete", account=account_name, synthesis=response_str)
                
        except Exception as e:
            if emit_event:
                emit_event("account_error", account=account_name, logic=str(e))
            print(f"******************* {account_name} FAILED *******************")
            print(e)
            response_err = "FAILED TO PROCESS"
            all_responses.append(response_err)
            mp_df.loc[mp_df["xero_names"] == account_name, "ai_summary"] = response_err

    # Persist results
    mp_df.to_csv(FILE_PATH_OUT)
    save_systematic_output(lines=all_responses, name=FILE_PATH_OUT)

if __name__ == "__main__":
    pass
