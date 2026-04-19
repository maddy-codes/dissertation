import pandas as pd
from datetime import date

def fetch_and_format_xero_data(xero_client, tenant_id: str, report_date: date):
    """
    Fetches Trial Balance and Profit & Loss from Xero,
    and constructs a structured dictionary simulating the tb_transactions_dict
    so the AI can generate reviews based purely on Xero APIs.
    """
    
    start_date = date(report_date.year - 1, report_date.month, report_date.day)
    
    # 1. Fetch Trial Balance
    tb_json = xero_client.get_trial_balance(tenant_id, report_date=report_date)
    
    # 2. Fetch P&L
    pl_json = xero_client.get_profit_and_loss(tenant_id, start_date=start_date, end_date=report_date)

    # 3. Fetch Accounts
    accounts_json = xero_client.get_accounts(tenant_id)
    account_lookup = {acc["AccountID"]: acc for acc in accounts_json.get("Accounts", [])}

    messages = []
    output_mapping_dataframe = {"xero_names": [], "xero_codes": [], "ai_summary": []}

    # Helper to parse Xero Reports Rows
    def extract_rows(rows, target_list):
        for r in rows:
            if r.get("RowType") == "Row":
                target_list.append(r)
            elif "Rows" in r:
                extract_rows(r["Rows"], target_list)

    tb_rows = []
    if tb_json.get("Reports"):
        extract_rows(tb_json["Reports"][0].get("Rows", []), tb_rows)

    pl_rows = []
    if pl_json.get("Reports"):
        extract_rows(pl_json["Reports"][0].get("Rows", []), pl_rows)

    # Iterate over TB rows to construct exactly what the AI needs
    for row in tb_rows:
        cells = row.get("Cells", [])
        if not cells or len(cells) < 1:
            continue
            
        account_val = cells[0].get("Value", "")
        if account_val == "Total":
            continue
            
        # P&L Context (if exists)
        pl_context = [p for p in pl_rows if len(p.get("Cells", [])) > 0 and p["Cells"][0].get("Value") == account_val]
        
        message_content = f"Xero Account Summary for {account_val}:\nTrial Balance Data: {str(cells)}\n"
        if pl_context:
            message_content += f"Profit & Loss Data: {str(pl_context[0].get('Cells', []))}\n"

        messages.append({
            "name": account_val,
            "message": message_content
        })
        
        output_mapping_dataframe["xero_names"].append(account_val)
        output_mapping_dataframe["xero_codes"].append(account_val.split("-")[0].strip() if "-" in account_val else "")
        output_mapping_dataframe["ai_summary"].append("")

    mp_df = pd.DataFrame(output_mapping_dataframe)
    
    return messages, mp_df
