import re

with open("templates/workbench.html", "r") as f:
    content = f.read()

# Remove the AI Recommend button
content = re.sub(
    r'<button id="btn-ai-recommend".*?Run AI Intelligence Scan\s*</button>',
    '',
    content,
    flags=re.DOTALL
)

# Update COA headers to include the drill down column
content = content.replace(
    '<div class="grid grid-cols-[auto_80px_1fr_100px_100px_200px] gap-4 bg-surface-container-low px-8 py-4 border-b border-outline-variant text-[10px] font-black uppercase tracking-[0.2em] text-primary">',
    '<div class="grid grid-cols-[auto_80px_1fr_100px_100px_200px_40px] gap-4 bg-surface-container-low px-8 py-4 border-b border-outline-variant text-[10px] font-black uppercase tracking-[0.2em] text-primary">'
)
content = content.replace(
    '<div class="text-right">Recommendation</div></div>',
    '<div class="text-right">Recommendation</div><div class="text-center"></div></div>'
)

# 1. Inside `fetch_tb` success: Replace COA row generation
old_coa_gen = """                // COA Row
                const cel = document.createElement("div");
                cel.id = `coa-row-${row.account.replace(/\\s+/g, '-')}`;
                cel.className = "coa-row grid grid-cols-[auto_80px_1fr_100px_100px_200px] gap-4 items-center px-8 py-5 border-b border-outline-variant/10 hover:bg-surface-container-low transition-all";
                cel.innerHTML = `<div><input type="checkbox" name="selected_nominal_codes" value="${row.account}" class="coa-check w-5 h-5 text-primary rounded-sm" form="final-form"></div><div class="font-mono text-[11px] font-black text-outline/60">${row.code}</div><p class="text-primary text-[13px] font-extrabold uppercase">${row.account}</p><div class="text-right text-[12px]">${row.prev_balance}</div><div class="text-right text-[12px] text-primary font-bold">${row.balance}</div><div class="rec-cell text-right text-[9px] font-bold text-outline uppercase tracking-widest">Awaiting Scan</div>`;
                coaCont.appendChild(cel);"""

new_coa_gen = """                // COA Row - Generated with drill-down container
                const celWrapper = document.createElement("div");
                celWrapper.className = "flex flex-col border-b border-outline-variant/10";
                
                const cel = document.createElement("div");
                const safeId = row.account.replace(/\\s+/g, '-');
                cel.id = `coa-row-${safeId}`;
                cel.className = "coa-row grid grid-cols-[auto_80px_1fr_100px_100px_200px_40px] gap-4 items-center px-8 py-5 hover:bg-surface-container-low transition-all";
                cel.innerHTML = `<div><input type="checkbox" name="selected_nominal_codes" value="${row.account}" class="coa-check w-5 h-5 text-primary rounded-sm" form="final-form"></div><div class="font-mono text-[11px] font-black text-outline/60">${row.code}</div><p class="text-primary text-[13px] font-extrabold uppercase">${row.account}</p><div class="text-right text-[12px]">${row.prev_balance}</div><div class="text-right text-[12px] text-primary font-bold">${row.balance}</div><div class="rec-cell text-right text-[9px] font-bold text-outline uppercase tracking-widest">Awaiting Scan</div><div class="text-center"><button type="button" class="btn-drilldown hidden text-outline hover:text-primary transition-colors"><span class="material-symbols-outlined text-lg">chevron_right</span></button></div>`;
                
                const drilldown = document.createElement("div");
                drilldown.id = `drilldown-${safeId}`;
                drilldown.className = "hidden bg-surface-container-low/50 px-10 py-4";
                drilldown.innerHTML = `<div class="text-[10px] font-black uppercase text-outline tracking-widest mb-3">Identified Transactions</div><div class="tx-list flex flex-col gap-2"></div>`;
                
                celWrapper.appendChild(cel);
                celWrapper.appendChild(drilldown);
                coaCont.appendChild(celWrapper);"""

content = content.replace(old_coa_gen, new_coa_gen)

# 2. Replace the btn-ai-recommend event listener with a processBatches function
# Since re.sub is tricky with big blocks, we'll just slice the string.
start_str = '// AI Intelligence Scan'
end_str = '// Navigation & Modals'

start_idx = content.find(start_str)
end_idx = content.find(end_str)

if start_idx != -1 and end_idx != -1:
    new_js = """// Async Batch Processing
    const processBatches = async () => {
        addThought("Intelligence", "Initiating asynchronous nominal analysis in batches...", "logic");
        statusText.innerText = "Scanning Patterns";
        agentDot.className = "h-2 w-2 rounded-full bg-secondary-container animate-pulse";
        
        const globalMat = document.getElementById("input-global-mat").value;
        const batchSize = 10;
        
        for (let i = 0; i < tbDataRaw.length; i += batchSize) {
            const batch = tbDataRaw.slice(i, i + batchSize);
            addThought("System", `Processing batch ${Math.floor(i/batchSize)+1}...`, "info");
            
            try {
                const res = await fetch(`/api/workbench/analyze_scope_batch/${tenantId}`, {
                    method: "POST",
                    headers: {"Content-Type": "application/json", "X-CSRFToken": "{{ csrf_token() }}"},
                    body: JSON.stringify({ tb_data: batch, global_materiality: globalMat })
                });
                const result = await res.json();
                
                if (result.status === "Success" && result.data && result.data.coa_suggestions) {
                    result.data.coa_suggestions.forEach(s => {
                        const safeAcc = s.account.replace(/\\s+/g, '-');
                        const row = document.getElementById(`coa-row-${safeAcc}`);
                        const drilldown = document.getElementById(`drilldown-${safeAcc}`);
                        if (row) {
                            const check = row.querySelector(".coa-check");
                            const rec = row.querySelector(".rec-cell");
                            const arrowBtn = row.querySelector(".btn-drilldown");
                            const txList = drilldown.querySelector(".tx-list");
                            
                            check.checked = s.should_analyze;
                            rec.innerHTML = `<span class="${s.should_analyze ? 'text-error' : 'text-outline/60'}">${s.should_analyze ? 'Analyze' : 'Skip'}</span><p class="normal-case text-[8px] text-outline tracking-normal mt-1 leading-tight">${s.reason}</p>`;
                            
                            if (s.should_analyze) {
                                // Highlight row red
                                row.classList.add("bg-error/5");
                                row.classList.remove("opacity-50");
                                
                                // Show drilldown arrow if there are transactions
                                if (s.transactions && s.transactions.length > 0) {
                                    arrowBtn.classList.remove("hidden");
                                    arrowBtn.addEventListener("click", () => {
                                        drilldown.classList.toggle("hidden");
                                        const icon = arrowBtn.querySelector("span");
                                        icon.innerText = drilldown.classList.contains("hidden") ? "chevron_right" : "expand_more";
                                    });
                                    
                                    // Populate transactions
                                    s.transactions.forEach(tx => {
                                        const txEl = document.createElement("div");
                                        txEl.className = "flex justify-between items-center bg-white p-3 rounded-sm border border-outline-variant/20 shadow-sm";
                                        const badgeClass = tx.type === 'subscription' ? 'bg-secondary-container text-secondary' : 'bg-error/10 text-error';
                                        txEl.innerHTML = `
                                            <div class="flex items-center gap-3">
                                                <span class="px-2 py-1 text-[8px] font-black uppercase tracking-wider rounded-sm ${badgeClass}">${tx.type}</span>
                                                <span class="text-xs font-bold text-primary">${tx.desc}</span>
                                                <span class="text-[10px] text-outline font-mono">${tx.date}</span>
                                            </div>
                                            <div class="font-black text-xs text-primary">£${tx.amount.toFixed(2)}</div>
                                        `;
                                        txList.appendChild(txEl);
                                    });
                                }
                            } else {
                                row.classList.add("opacity-50");
                            }
                        }
                    });
                }
            } catch (err) {
                console.error(err);
            }
        }
        
        addThought("System", "Batch analysis completed. Workspace saved as DRAFT.", "success");
        statusText.innerText = "Live Scan";
        agentDot.className = "h-2 w-2 rounded-full bg-secondary-container";
        
        // Save draft via endpoint
        fetch(`/api/workbench/save_draft/${tenantId}`, {
            method: "POST",
            headers: {"Content-Type": "application/json", "X-CSRFToken": "{{ csrf_token() }}"},
            body: JSON.stringify({ current_year_end: currentYearEnd, comparison_year_end: comparisonYearEnd })
        });
    };

    """
    content = content[:start_idx] + new_js + content[end_idx:]

# 3. Trigger processBatches when transitioning to COA stage
content = content.replace(
    'document.getElementById("btn-to-coa").addEventListener("click", () => { activePill(2); transitionTo(stageTb, stageCoa, 300); });',
    'document.getElementById("btn-to-coa").addEventListener("click", () => { activePill(2); transitionTo(stageTb, stageCoa, 300); processBatches(); });'
)

with open("templates/workbench.html", "w") as f:
    f.write(content)

print("Patched workbench.html")
