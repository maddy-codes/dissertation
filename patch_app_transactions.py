import re

with open("app.py", "r") as f:
    content = f.read()

new_route = """@app.route("/api/workbench/nominal_transactions/<tenant_id>", methods=["GET"])
@login_required
def nominal_transactions(tenant_id):
    from integrations.xero_api import XeroClient
    from datetime import date
    from dateutil.relativedelta import relativedelta
    import traceback

    account_code = request.args.get("account_code")
    current_year_end = request.args.get("current_year_end")
    if not account_code or not current_year_end:
        return jsonify({"status": "Error", "message": "Missing parameters"}), 400

    token_data = current_user.get_xero_token()
    if not token_data:
        return jsonify({"status": "Error", "message": "No Xero token"}), 400

    try:
        xero_client = XeroClient(
            client_id=os.environ.get("XERO_CLIENT_ID"),
            client_secret=os.environ.get("XERO_CLIENT_SECRET"),
            refresh_token=token_data.get("refresh_token"),
            user=current_user
        )
        
        # 1. Map code to account ID
        accounts = xero_client.get_accounts(tenant_id)
        account_id = None
        for acc in accounts.get("Accounts", []):
            if acc.get("Code") == account_code:
                account_id = acc.get("AccountID")
                break
                
        if not account_id:
            return jsonify({"status": "Success", "transactions": []})
            
        # 2. Fetch Detailed Transaction Report for current year
        report_date = date.fromisoformat(current_year_end)
        start_date = report_date - relativedelta(years=1) + relativedelta(days=1)
        
        tx_report = xero_client.get_detailed_transaction_report(
            tenant_id=tenant_id, 
            start_date=start_date, 
            end_date=report_date, 
            account_id=account_id
        )
        
        # Parse the report to extract transactions
        transactions = []
        if tx_report.get("Reports"):
            for row in tx_report["Reports"][0].get("Rows", []):
                # The section with transactions usually has RowType = Section
                if row.get("RowType") == "Section":
                    for inner_row in row.get("Rows", []):
                        if inner_row.get("RowType") == "Row":
                            cells = inner_row.get("Cells", [])
                            if len(cells) >= 5:
                                tx_date = cells[0].get("Value", "")
                                desc = cells[1].get("Value", "") or cells[2].get("Value", "")
                                try:
                                    amount_str = cells[5].get("Value", "0").replace(',', '')
                                    amount = float(amount_str) if amount_str else 0.0
                                except ValueError:
                                    amount = 0.0
                                    
                                transactions.append({
                                    "date": tx_date,
                                    "desc": desc,
                                    "amount": amount,
                                    "type": "transaction"
                                })
                                
        # Sort and limit to top 10 for display purposes (or filter by subscriptions if possible)
        transactions = sorted(transactions, key=lambda x: abs(x["amount"]), reverse=True)[:10]
        
        return jsonify({"status": "Success", "transactions": transactions})
    except Exception as e:
        print(f"Error fetching transactions: {traceback.format_exc()}")
        return jsonify({"status": "Error", "message": str(e)}), 500

"""

# Insert before prime_ledger
pattern = r'@app\.route\("/api/workbench/prime_ledger/<tenant_id>", methods=\["GET"\]\)'
content = re.sub(pattern, new_route + '\n' + pattern, content)

with open("app.py", "w") as f:
    f.write(content)
