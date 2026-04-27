import numpy as np
from collections import defaultdict
from typing import List, Dict, Any

def analyze_ledger(current_txs: List[Dict[str, Any]], prior_txs: List[Dict[str, Any]]) -> str:
    """
    Analyzes transactions for a specific account code.
    tx format: {'Description': str, 'Amount': float, 'Date': str}
    """
    if not current_txs and not prior_txs:
        return "No transactions found for this account."

    def get_key(tx):
        desc = tx.get('Description', '').strip()
        return desc if desc else "Unknown"

    curr_by_key = defaultdict(list)
    for tx in current_txs:
        key = get_key(tx)
        amt = abs(float(tx.get('Amount', 0)))
        if amt > 0:
            curr_by_key[key].append({'Amount': amt, 'Date': tx.get('Date', '')})

    prior_by_key = defaultdict(list)
    for tx in prior_txs:
        key = get_key(tx)
        amt = abs(float(tx.get('Amount', 0)))
        if amt > 0:
            prior_by_key[key].append({'Amount': amt, 'Date': tx.get('Date', '')})

    # 1. BIG Transactions (Top 5 in current year)
    sorted_curr = sorted(current_txs, key=lambda x: abs(float(x.get('Amount', 0))), reverse=True)
    top_5_big = sorted_curr[:5]

    # 2. New Transactions (present in current, not in prior)
    new_transactions = []
    for key, txs in curr_by_key.items():
        if key not in prior_by_key and key != "Unknown":
            total_amt = sum(t['Amount'] for t in txs)
            new_transactions.append((key, total_amt))
    new_transactions.sort(key=lambda x: x[1], reverse=True)

    # 3. Subscriptions & Drops/Spikes (> 2 S.D.)
    subscriptions = []
    subscription_anomalies = []
    
    # Analyze across both years to establish pattern
    for key in set(curr_by_key.keys()).union(prior_by_key.keys()):
        if key == "Unknown":
            continue
            
        all_txs = prior_by_key.get(key, []) + curr_by_key.get(key, [])
        if len(all_txs) >= 3: # Consider it a recurring subscription if 3+ occurrences
            amounts = [t['Amount'] for t in all_txs]
            mean_amt = np.mean(amounts)
            std_amt = np.std(amounts)
            
            # Anomalies (Drop or Spike > 2 S.D.)
            if std_amt > 0:
                upper_bound = mean_amt + (2 * std_amt)
                lower_bound = max(0, mean_amt - (2 * std_amt))
                
                for tx in curr_by_key.get(key, []):
                    amt = tx['Amount']
                    if amt > upper_bound or amt < lower_bound:
                        direction = "Drop" if amt < lower_bound else "Spike"
                        subscription_anomalies.append(
                            f"- {key}: {direction} to £{amt:,.2f} on {tx['Date']} (Historical Mean: £{mean_amt:,.2f})"
                        )
            
            curr_count = len(curr_by_key.get(key, []))
            if curr_count > 0:
                curr_total = sum(t['Amount'] for t in curr_by_key.get(key, []))
                subscriptions.append(f"- {key}: {curr_count} payments, Avg £{mean_amt:,.2f} (Total £{curr_total:,.2f})")

    # Output formatting
    lines = []
    
    if subscriptions:
        lines.append("=== RECURRING SUBSCRIPTIONS ===")
        lines.extend(subscriptions[:15]) # Limit to top 15 subscriptions
        lines.append("")

    if new_transactions:
        lines.append("=== NEW TRANSACTIONS (Descriptions/Vendors unseen last year) ===")
        for key, total in new_transactions[:10]: # Limit to top 10
            lines.append(f"- {key} (Total spend: £{total:,.2f})")
        lines.append("")

    if top_5_big:
        lines.append("=== BIG TRANSACTIONS (TOP 5) ===")
        for tx in top_5_big:
            lines.append(f"- {get_key(tx)}: £{abs(float(tx.get('Amount', 0))):,.2f} on {tx.get('Date', 'Unknown')}")
        lines.append("")
        
    if subscription_anomalies:
        lines.append("=== SUBSCRIPTION ANOMALIES (> 2 S.D. drop/spike from mean) ===")
        lines.extend(subscription_anomalies[:10]) # Limit to top 10
        lines.append("")

    if not lines:
        return "No notable transactional patterns identified."
        
    return "\n".join(lines).strip()
