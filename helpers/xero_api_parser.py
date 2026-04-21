import pandas as pd
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

def fetch_and_format_xero_data(xero_client, tenant_id: str, report_date: date, comparison_date: date = None):
    """
    Fetches Trial Balance and Profit & Loss from Xero,
    and constructs a structured dictionary simulating the tb_transactions_dict
    so the AI can generate reviews based purely on Xero APIs.
    """
    
    # Financial year usually spans exactly 1 year (e.g. 1st April to 31st March)
    start_date = report_date - relativedelta(years=1) + timedelta(days=1)
    
    # 1. Fetch Trial Balance
    tb_json = xero_client.get_trial_balance(tenant_id, report_date=report_date)
    
    # 2. Fetch P&L
    pl_json = xero_client.get_profit_and_loss(tenant_id, start_date=start_date, end_date=report_date)

    # Fetch Prior Year data if requested
    comp_tb_json = None
    comp_pl_json = None
    if comparison_date:
        comp_start = comparison_date - relativedelta(years=1) + timedelta(days=1)
        try:
            comp_tb_json = xero_client.get_trial_balance(tenant_id, report_date=comparison_date)
            comp_pl_json = xero_client.get_profit_and_loss(tenant_id, start_date=comp_start, end_date=comparison_date)
        except Exception as e:
            print(f"Failed to fetch comparison data: {e}")

    # 3. Fetch Accounts
    try:
        accounts_json = xero_client.get_accounts(tenant_id)
        account_lookup = {acc["AccountID"]: acc for acc in accounts_json.get("Accounts", [])}
    except Exception:
        pass

    messages = []
    output_mapping_dataframe = {"xero_names": [], "xero_codes": [], "ai_summary": []}

    # 4. Fetch Bank Transactions and get subscriptions
    try:
        bank_txs_json = xero_client.get_bank_transactions(tenant_id)
        from experiments.types import Example, SubscriptionPolicy
        from experiments.context.subscriptions import summarise_subscriptions
        
        mock_example = Example(example_id="api", transactions=bank_txs_json.get("BankTransactions", []))
        sys_subs = summarise_subscriptions(mock_example, SubscriptionPolicy())
    except Exception as e:
        sys_subs = f"SUBSCRIPTIONS_SUMMARY (error fetching transactions: {e})"

    # Helper to parse Xero Reports Rows
    def extract_rows(rows, target_list):
        for r in rows:
            if r.get("RowType") == "Row":
                target_list.append(r)
            elif "Rows" in r:
                extract_rows(r["Rows"], target_list)

    tb_rows = []
    if tb_json and tb_json.get("Reports"):
        extract_rows(tb_json["Reports"][0].get("Rows", []), tb_rows)

    pl_rows = []
    if pl_json and pl_json.get("Reports"):
        extract_rows(pl_json["Reports"][0].get("Rows", []), pl_rows)
        
    comp_tb_rows = []
    if comp_tb_json and comp_tb_json.get("Reports"):
        extract_rows(comp_tb_json["Reports"][0].get("Rows", []), comp_tb_rows)
        
    comp_pl_rows = []
    if comp_pl_json and comp_pl_json.get("Reports"):
        extract_rows(comp_pl_json["Reports"][0].get("Rows", []), comp_pl_rows)

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
        
        # Comparative Context
        comp_tb_context = [p for p in comp_tb_rows if len(p.get("Cells", [])) > 0 and p["Cells"][0].get("Value") == account_val]
        comp_pl_context = [p for p in comp_pl_rows if len(p.get("Cells", [])) > 0 and p["Cells"][0].get("Value") == account_val]
        
        message_content = f"Xero Account Summary for {account_val}:\nTrial Balance Data: {str(cells)}\n"
        if pl_context:
            message_content += f"Profit & Loss Data: {str(pl_context[0].get('Cells', []))}\n"
            
        if comp_tb_context:
            message_content += f"Prior Year Trial Balance Data: {str(comp_tb_context[0].get('Cells', []))}\n"
        if comp_pl_context:
            message_content += f"Prior Year Profit & Loss Data: {str(comp_pl_context[0].get('Cells', []))}\n"

        # Prepend Subscription Summary on the first valid message we create (to give context)
        if not messages and sys_subs:
            message_content = f"==== CORE INSIGHT: RECURRING SUBSCRIPTIONS ====\n{sys_subs}\n===============================================\n\n" + message_content

        messages.append({
            "name": account_val,
            "message": message_content
        })
        
        output_mapping_dataframe["xero_names"].append(account_val)
        output_mapping_dataframe["xero_codes"].append(account_val.split("-")[0].strip() if "-" in account_val else "")
        output_mapping_dataframe["ai_summary"].append("")

    mp_df = pd.DataFrame(output_mapping_dataframe)
    
    return messages, mp_df
