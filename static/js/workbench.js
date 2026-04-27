document.addEventListener("DOMContentLoaded", async () => {
    let tbDataRaw = [];
    let draftMap = {};
    let allSuggestions = [];
    
    const stageTb = document.getElementById("stage-tb");
    const stageCoa = document.getElementById("stage-coa");
    const stageAnalysis = document.getElementById("stage-analysis");
    const stageFinal = document.getElementById("stage-final");
    const pills = [1,2,3,4].map(n => document.getElementById(`pill-${n}`));
    const stream = document.getElementById("thought-stream");
    const statusText = document.getElementById("agent-status-text");
    const agentDot = document.querySelector("#agent-badge div");

    const activePill = (n) => {
        pills.forEach((p, i) => {
            p.className = (i+1 === n) ? "px-4 py-2 rounded-sm text-[10px] font-black uppercase tracking-[0.2em] bg-primary text-white shadow-md transition-all duration-300 scale-105" :
                         (i+1 < n) ? "px-4 py-2 rounded-sm text-[10px] font-black uppercase tracking-[0.2em] bg-primary/5 text-primary border border-primary/20 transition-all duration-300" :
                         "px-4 py-2 rounded-sm text-[10px] font-black uppercase tracking-[0.2em] bg-surface-container text-outline border border-outline-variant/20 transition-all duration-300";
        });
    };

    const addThought = (tag, text, type = "info") => {
        const d = document.createElement("div");
        let tagClass = "text-secondary";
        if (type === "error") tagClass = "text-error";
        if (type === "success") tagClass = "text-green-600";
        if (type === "logic") tagClass = "text-primary";
        d.className = "flex gap-3 bg-surface-container-low/50 px-4 py-3 rounded-sm border-l-2 border-outline-variant/30 animate-in fade-in slide-in-from-left-2";
        d.innerHTML = `<span class="font-black shrink-0 ${tagClass} uppercase text-[9px] tracking-widest">[${tag}]</span><span class="text-on-surface-variant font-bold text-[11px] font-mono leading-relaxed">${text}</span>`;
        stream.appendChild(d);
        stream.scrollTop = stream.scrollHeight;
    };

    const transitionTo = (hideEl, showEl, delay = 0) => {
        hideEl.style.opacity = "0";
        setTimeout(() => {
            hideEl.classList.add("hidden");
            showEl.classList.remove("hidden");
            showEl.classList.add("flex");
            requestAnimationFrame(() => { showEl.style.opacity = "1"; });
        }, delay);
    };
    
    const saveDraft = () => {
        fetch(`/api/workbench/save_draft/${CONFIG.tenantId}`, {
            method: "POST",
            headers: {"Content-Type": "application/json", "X-CSRFToken": CONFIG.csrfToken},
            body: JSON.stringify({ 
                current_year_end: CONFIG.currentYearEnd, 
                comparison_year_end: CONFIG.comparisonYearEnd,
                draft_state: allSuggestions 
            })
        });
    };

    // Load Draft if exists
    activePill(1);
    try {
        const draftRes = await fetch(`/api/workbench/load_draft/${CONFIG.tenantId}`);
        const draftData = await draftRes.json();
        if (draftData.status === "Success" && draftData.draft_state) {
            allSuggestions = draftData.draft_state;
            allSuggestions.forEach(s => {
                draftMap[s.account] = s;
            });
            addThought("System", `Loaded previous draft state with ${allSuggestions.length} records.`, "success");
        }
    } catch(e) {
        console.error("Draft load error", e);
    }

    // Load Ledger
    addThought("System", "Bypassing init stage. Loading direct ledger access...", "logic");

    fetch(`/api/workbench/fetch_tb/${CONFIG.tenantId}?current_year_end=${CONFIG.currentYearEnd}&comparison_year_end=${CONFIG.comparisonYearEnd}`)
        .then(res => res.json())
        .then(data => {
            if (data.status !== "Success") { addThought("Critical", data.message, "error"); return; }
            document.getElementById("tb-loading").remove();
            tbDataRaw = data.tb_raw;
            const rowsCont = document.getElementById("tb-rows");
            const coaCont = document.getElementById("coa-cards");
            
            data.tb_raw.forEach(row => {
                // TB Row
                const rel = document.createElement("div");
                rel.className = "grid grid-cols-[80px_1fr_100px_100px_100px_100px] gap-4 items-center px-8 py-4 border-b border-outline-variant/10 hover:bg-surface-container-low bg-white";
                rel.innerHTML = `<div class="font-mono text-[11px] font-black text-outline/60">${row.code}</div><div class="text-primary text-[12px] font-bold uppercase">${row.account}</div><div class="text-right text-[11px]">${row.prev_balance}</div><div class="text-right text-[11px]">${row.debit}</div><div class="text-right text-[11px]">${row.credit}</div><div class="text-right font-black text-primary">${row.balance}</div>`;
                rowsCont.appendChild(rel);

                // COA Row - Generated with drill-down container
                const celWrapper = document.createElement("div");
                celWrapper.className = "flex flex-col border-b border-outline-variant/10";
                
                const safeId = row.account.replace(/\s+/g, '-');
                const cel = document.createElement("div");
                cel.id = `coa-row-${safeId}`;
                cel.className = "coa-row grid grid-cols-[auto_80px_1fr_100px_100px_200px_40px] gap-4 items-center px-8 py-5 hover:bg-surface-container-low transition-all";
                cel.innerHTML = `<div><input type="checkbox" name="selected_nominal_codes" value="${row.account}" class="coa-check w-5 h-5 text-primary rounded-sm" form="final-form"></div><div class="font-mono text-[11px] font-black text-outline/60">${row.code}</div><p class="text-primary text-[13px] font-extrabold uppercase">${row.account}</p><div class="text-right text-[12px]">${row.prev_balance}</div><div class="text-right text-[12px] text-primary font-bold">${row.balance}</div><div class="rec-cell text-right text-[9px] font-bold text-outline uppercase tracking-widest">Awaiting Scan</div><div class="text-center"><button type="button" class="btn-drilldown hidden text-outline hover:text-primary transition-colors"><span class="material-symbols-outlined text-lg">chevron_right</span></button></div>`;
                
                const drilldown = document.createElement("div");
                drilldown.id = `drilldown-${safeId}`;
                drilldown.className = "hidden bg-surface-container-low/50 px-10 py-4";
                drilldown.innerHTML = `<div class="text-[10px] font-black uppercase text-outline tracking-widest mb-3">Live Transaction Stream (Current Year)</div><div class="tx-list flex flex-col gap-2"></div>`;
                
                celWrapper.appendChild(cel);
                celWrapper.appendChild(drilldown);
                coaCont.appendChild(celWrapper);
                
                // If we have draft state for this row, apply it immediately
                if (draftMap[row.account]) {
                    const s = draftMap[row.account];
                    applySuggestionToRow(s, row.account, row.code);
                }
            });
            addThought("Insight", `Synchronized ${data.tb_raw.length} identities.`, "success");
        });

    const loadTransactions = async (accountCode, accountName, txListContainer) => {
        txListContainer.innerHTML = `<div class="text-[10px] text-outline font-black uppercase tracking-widest animate-pulse py-4">Fetching live data from ledger...</div>`;
        try {
            const res = await fetch(`/api/workbench/nominal_transactions/${CONFIG.tenantId}?account_code=${encodeURIComponent(accountCode || '')}&account_name=${encodeURIComponent(accountName || '')}&current_year_end=${CONFIG.currentYearEnd}`);
            const data = await res.json();
            txListContainer.innerHTML = "";
            if (data.status === "Success") {
                if (!data.transactions || data.transactions.length === 0) {
                    txListContainer.innerHTML = `<div class="text-xs text-outline italic py-2">No material transactions identified.</div>`;
                    return;
                }
                data.transactions.forEach(tx => {
                    const txEl = document.createElement("div");
                    txEl.className = "flex justify-between items-center bg-white p-3 rounded-sm border border-outline-variant/20 shadow-sm";
                    const isSub = (tx.desc && tx.desc.toLowerCase().includes("sub")) ? true : false;
                    const badgeClass = isSub ? 'bg-secondary-container text-secondary' : 'bg-primary/10 text-primary';
                    const txTypeStr = isSub ? "Subscription" : "Payment";
                    txEl.innerHTML = `
                        <div class="flex items-center gap-3">
                            <span class="px-2 py-1 text-[8px] font-black uppercase tracking-wider rounded-sm ${badgeClass}">${txTypeStr}</span>
                            <span class="text-xs font-bold text-primary">${tx.desc || 'System Transaction'}</span>
                            <span class="text-[10px] text-outline font-mono">${tx.date}</span>
                        </div>
                        <div class="font-black text-xs text-primary">£${tx.amount.toFixed(2)}</div>
                    `;
                    txListContainer.appendChild(txEl);
                });
            } else {
                txListContainer.innerHTML = `<div class="text-xs text-error py-2">Failed to load: ${data.message}</div>`;
            }
        } catch (e) {
            txListContainer.innerHTML = `<div class="text-xs text-error py-2">Network error fetching transactions.</div>`;
        }
    };

    const applySuggestionToRow = (s, accountName, accountCode) => {
        const safeAcc = accountName.replace(/\s+/g, '-');
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
                
                // Always show drilldown for analyzed
                arrowBtn.classList.remove("hidden");
                // Remove existing listeners if any by cloning
                const newBtn = arrowBtn.cloneNode(true);
                arrowBtn.parentNode.replaceChild(newBtn, arrowBtn);
                
                newBtn.addEventListener("click", () => {
                    drilldown.classList.toggle("hidden");
                    const icon = newBtn.querySelector("span");
                    icon.innerText = drilldown.classList.contains("hidden") ? "chevron_right" : "expand_more";
                    
                    // If opening and not loaded yet
                    if (!drilldown.classList.contains("hidden") && txList.innerHTML === "") {
                        loadTransactions(accountCode, accountName, txList);
                    }
                });
            } else {
                row.classList.add("opacity-50");
                row.classList.remove("bg-error/5");
                arrowBtn.classList.add("hidden");
            }
        }
    };

    // Async Batch Processing
    const processBatches = async () => {
        // Find un-analyzed rows
        const unanalyzed = tbDataRaw.filter(row => !draftMap[row.account]);
        
        if (unanalyzed.length === 0) {
            addThought("System", "All nominals already analyzed from draft.", "success");
            return;
        }
        
        addThought("Intelligence", `Initiating asynchronous AI analysis for ${unanalyzed.length} nominals...`, "logic");
        statusText.innerText = "Scanning Patterns";
        agentDot.className = "h-2 w-2 rounded-full bg-secondary-container animate-pulse";
        
        const globalMat = document.getElementById("input-global-mat").value;
        const batchSize = 10;
        
        for (let i = 0; i < unanalyzed.length; i += batchSize) {
            const batch = unanalyzed.slice(i, i + batchSize);
            addThought("System", `Processing batch ${Math.floor(i/batchSize)+1}...`, "info");
            
            try {
                const res = await fetch(`/api/workbench/analyze_scope_batch/${CONFIG.tenantId}`, {
                    method: "POST",
                    headers: {"Content-Type": "application/json", "X-CSRFToken": CONFIG.csrfToken},
                    body: JSON.stringify({ tb_data: batch, global_materiality: globalMat })
                });
                const result = await res.json();
                
                if (result.status === "Success" && result.data && result.data.coa_suggestions) {
                    result.data.coa_suggestions.forEach(s => {
                        // Store the suggestion
                        draftMap[s.account] = s;
                        allSuggestions.push(s);
                        
                        applySuggestionToRow(s, s.account, s.code);
                    });
                    // Save draft after each successful batch
                    saveDraft();
                }
            } catch (err) {
                console.error(err);
            }
        }
        
        addThought("System", "Batch AI analysis completed. Workspace saved as DRAFT.", "success");
        statusText.innerText = "Live Scan";
        agentDot.className = "h-2 w-2 rounded-full bg-secondary-container";
    };

    // Navigation & Modals
    document.getElementById("btn-to-coa").addEventListener("click", () => { 
        activePill(2); 
        transitionTo(stageTb, stageCoa, 300); 
        processBatches(); 
    });
    
    document.getElementById("btn-approve-all").addEventListener("click", () => { 
        document.querySelectorAll(".coa-check").forEach(c => { 
            c.checked = true; 
            c.closest(".coa-row").classList.remove("opacity-50"); 
        }); 
        addThought("Operator", "Bulk selection authorized.", "success"); 
    });
    
    document.getElementById("btn-materiality").addEventListener("click", () => { 
        const m = document.getElementById("modal-materiality"); 
        m.classList.remove("hidden"); 
        m.classList.add("flex"); 
        setTimeout(() => m.classList.add("opacity-100"), 10); 
    });
    
    document.querySelectorAll(".modal-close").forEach(b => b.addEventListener("click", () => { 
        const m = document.getElementById("modal-materiality"); 
        m.classList.remove("opacity-100"); 
        setTimeout(() => m.classList.add("hidden"), 300); 
    }));

    document.getElementById("btn-save-mat").addEventListener("click", () => { 
        addThought("Config", "New materiality thresholds committed.", "success"); 
        const m = document.getElementById("modal-materiality"); 
        m.classList.remove("opacity-100"); 
        setTimeout(() => m.classList.add("hidden"), 300); 
    });

    // Transition to Analysis
    document.getElementById("btn-to-analysis").addEventListener("click", () => {
        const checked = document.querySelectorAll(".coa-check:checked");
        document.getElementById("analysis-total").innerText = checked.length;
        document.getElementById("analysis-empty-state").classList.add("hidden");
        activePill(3);
        transitionTo(stageCoa, stageAnalysis, 300);
        
        let i = 0;
        checked.forEach(c => {
            setTimeout(() => {
                const card = document.createElement("div");
                card.className = "bg-white p-6 border border-outline-variant/20 rounded-sm shadow-sm flex items-center gap-4";
                card.innerHTML = `<span class="material-symbols-outlined text-green-600">verified</span><p class="text-primary font-black uppercase text-xs">${c.value}</p><span class="text-[9px] text-outline ml-auto uppercase font-black">Ready for Crew</span>`;
                document.getElementById("analysis-cards").appendChild(card);
                i++;
                document.getElementById("analysis-current").innerText = i;
                if (i === checked.length) document.getElementById("btn-to-final").classList.remove("hidden");
            }, i * 150);
        });
    });

    document.getElementById("btn-to-final").addEventListener("click", () => { 
        activePill(4); 
        transitionTo(stageAnalysis, stageFinal, 300); 
    });
});