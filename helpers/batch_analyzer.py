import json
import os
from typing import List, Dict, Any
from openai import AzureOpenAI

def analyze_nominal_batch(batch: List[Dict[str, Any]], global_mat: float) -> List[Dict[str, Any]]:
    """
    Uses an AI Agent to determine which nominal accounts should be analyzed
    based on the firm's guidelines and materiality.
    """
    # Import inside to avoid circular dependencies if any, though strings is standalone
    from strings.assistant import API_VERSION, DEPLOYED_MODEL_NAME
    
    client = AzureOpenAI(
        api_key=os.environ.get("AZURE_OPENAI_API_KEY"),
        api_version=API_VERSION,
        azure_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT")
    )

    # Simplify the batch data to reduce token usage
    context_lines = []
    for row in batch:
        context_lines.append(f"Account: '{row.get('account', '')}' (Code: {row.get('code', '')}), Current Balance: {row.get('balance', '0')}, Prior Year: {row.get('prev_balance', '0')}")
        
    context_str = "\n".join(context_lines)
    
    prompt = f"""
    You are an expert UK accounting AI assistant. Review this excerpt of Xero Trial Balance data:
    
    {context_str}
    
    The Global Materiality threshold is £{global_mat}.
    
    Guidelines for selection (Accounts Review Page Notes):
    Always analyze: Directors Remuneration, Legal Fees, Sundry, Professional Fees, Donations, Entertainment, Bad Debts.
    Always analyze: Anything new this year (i.e. NIL in previous year).
    Always analyze: Anything NIL this year (where there was a cost last year).
    Always analyze: Profit/Loss on Assets, Deferred Tax, Fixed Assets additions/disposals, Stock, Debtors, Prepayments, Cash at bank, Creditors, PAYE CT and VAT, DLA.
    Also analyze if there is a variance greater than the Global Materiality threshold.
    Also analyze Subscription/IT/Software costs.

    For each account in the provided excerpt, determine if it should be analyzed based on the above rules.
    
    Respond STRICTLY with a JSON object containing a "results" array:
    {{
      "results": [
        {{
          "account": "Exact Account Name",
          "should_analyze": true/false,
          "reason": "Brief explanation of why it was selected or skipped based on the rules.",
          "type": "subscription / outlier / variance / guideline / none"
        }}
      ]
    }}
    """
    
    try:
        response = client.chat.completions.create(
            model=DEPLOYED_MODEL_NAME,
            messages=[
                {"role": "system", "content": "You are a JSON-producing accounting assistant."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"}
        )
        
        response_json = json.loads(response.choices[0].message.content)
        ai_results = response_json.get("results", [])
    except Exception as e:
        print(f"AI batch analysis failed: {e}")
        # Fallback to empty if AI fails
        ai_results = []
        
    # Merge AI results back into the batch order and add mock transactions
    ai_dict = {item.get("account", "").lower().strip(): item for item in ai_results}
    
    final_results = []
    for row in batch:
        acc_name = row.get("account", "")
        acc_name_lower = acc_name.lower().strip()
        code = row.get("code", "")
        
        ai_eval = ai_dict.get(acc_name_lower, {})
        should_analyze = ai_eval.get("should_analyze", False)
        reason = ai_eval.get("reason", "No specific reason provided.")
        eval_type = ai_eval.get("type", "none")
        
        try:
            curr_str = str(row.get("balance", "0")).replace(',', '').replace('(', '-').replace(')', '')
            curr_val = float(curr_str) if curr_str else 0.0
        except ValueError:
            curr_val = 0.0
            
        try:
            prev_str = str(row.get("prev_balance", "0")).replace(',', '').replace('(', '-').replace(')', '')
            prev_val = float(prev_str) if prev_str else 0.0
        except ValueError:
            prev_val = 0.0
                
        final_results.append({
            "account": acc_name,
            "code": code,
            "should_analyze": should_analyze,
            "reason": reason
        })
        
    return final_results
