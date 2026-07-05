document.addEventListener("DOMContentLoaded", async () => {
    let tbDataRaw = [];
    let draftMap = {};
    let allSuggestions = [];
    let tbSearchTerm = "";
    let hideZeroBalances = false;
    let notesMap = {};

    const stageTb = document.getElementById("stage-tb");
    const stageCoa = document.getElementById("stage-coa");
    const stageAnalysis = document.getElementById("stage-analysis");
    const stageFinal = document.getElementById("stage-final");
    const pills = [1,2,3,4].map(n => document.getElementById(`pill-${n}`));
    const stream = document.getElementById("thought-stream");
    const statusText = document.getElementById("agent-status-text");
    const agentDot = document.querySelector("#agent-badge div");
    const tbModalBackdrop = document.getElementById("tb-modal-backdrop");

    const refreshIcons = () => { if (window.lucide) lucide.createIcons(); };

    // Modal card floats with a margin above a dimmed backdrop (same language as
    // #modal-materiality) rather than filling the viewport edge-to-edge, so it
    // reads as an overlay and not just the page taking over.
    //
    // Position/inset/z-index are set as inline styles rather than Tailwind
    // classes: the CDN's runtime compiler only generates CSS for utilities it
    // has already seen elsewhere in the static HTML, and "inset-6"/"z-[200]"
    // appear nowhere else — toggling them silently produced no rule at all,
    // leaving the card unconstrained and overflowing past the viewport edge.
    const EXPAND_MODAL_CLASSES = ["bg-surface", "overflow-y-auto", "rounded-lg", "border", "border-border-hairline", "shadow-lift"];
    let closeActiveExpand = null;

    // Wires an expand/collapse button pair onto a stage so it can pop out into
    // a full-screen modal card. Returns the toggle fn so callers (step
    // transitions) can force it closed when navigating away.
    const makeExpandable = (stageEl, btnExpand, btnCollapse, rowsEl, rowsDefaultMax, rowsExpandedMax) => {
        const setExpanded = (on) => {
            EXPAND_MODAL_CLASSES.forEach(c => stageEl.classList.toggle(c, on));
            if (on) {
                const margin = window.matchMedia("(min-width: 768px)").matches ? "48px" : "16px";
                Object.assign(stageEl.style, {
                    position: "fixed",
                    top: margin, left: margin, right: margin, bottom: margin,
                    zIndex: "200",
                });
                closeActiveExpand = setExpanded;
            } else {
                ["position", "top", "left", "right", "bottom", "zIndex"].forEach(k => { stageEl.style[k] = ""; });
                if (closeActiveExpand === setExpanded) closeActiveExpand = null;
            }
            if (rowsEl) rowsEl.style.maxHeight = on ? rowsExpandedMax : rowsDefaultMax;
            document.body.classList.toggle("overflow-hidden", on);
            btnExpand.classList.toggle("hidden", on);
            btnCollapse.classList.toggle("hidden", !on);
            btnCollapse.classList.toggle("flex", on);
            if (on) {
                tbModalBackdrop.classList.remove("hidden");
                requestAnimationFrame(() => { tbModalBackdrop.style.opacity = "1"; });
            } else {
                tbModalBackdrop.style.opacity = "0";
                setTimeout(() => tbModalBackdrop.classList.add("hidden"), 300);
            }
            refreshIcons();
        };
        btnExpand.addEventListener("click", () => setExpanded(true));
        btnCollapse.addEventListener("click", () => setExpanded(false));
        return setExpanded;
    };

    const setTbFullscreen = makeExpandable(
        stageTb,
        document.getElementById("btn-expand-tb"),
        document.getElementById("btn-collapse-tb"),
        document.getElementById("tb-rows"),
        "480px", "calc(100vh - 380px)"
    );
    const setCoaFullscreen = makeExpandable(
        stageCoa,
        document.getElementById("btn-expand-coa"),
        document.getElementById("btn-collapse-coa"),
        document.getElementById("coa-cards"),
        "400px", "calc(100vh - 340px)"
    );

    tbModalBackdrop.addEventListener("click", () => { if (closeActiveExpand) closeActiveExpand(false); });
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && closeActiveExpand) closeActiveExpand(false);
    });

    const activePill = (n) => {
        pills.forEach((p, i) => {
            p.className = (i+1 === n) ? "px-4 py-2.5 rounded-full font-mono text-[10px] uppercase tracking-[0.14em] bg-primary text-secondary transition-all duration-300 scale-105" :
                         (i+1 < n) ? "px-4 py-2.5 rounded-full font-mono text-[10px] uppercase tracking-[0.14em] bg-primary/10 text-secondary border border-primary/30 transition-all duration-300" :
                         "px-4 py-2.5 rounded-full font-mono text-[10px] uppercase tracking-[0.14em] text-on-surface-muted transition-all duration-300";
        });
    };

    const addThought = (tag, text, type = "info") => {
        const d = document.createElement("div");
        let tagClass = "text-on-surface-muted";
        if (type === "error") tagClass = "text-error";
        if (type === "success") tagClass = "text-success";
        if (type === "logic") tagClass = "text-secondary";
        d.className = "flex gap-3 bg-neutral/60 px-4 py-3 rounded-md border-l-2 border-border-hairline animate-in fade-in slide-in-from-left-2";
        d.innerHTML = `<span class="font-bold shrink-0 ${tagClass} uppercase text-[9px] tracking-widest font-mono">[${tag}]</span><span class="text-on-surface-muted font-semibold text-[11px] font-mono leading-relaxed">${text}</span>`;
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

    // Parse a Xero balance cell string ("1,667.00", "(1,667.00)") into a float.
    const parseBalance = (raw) => {
        const s = String(raw ?? "0").replace(/,/g, "").replace("(", "-").replace(")", "");
        const n = parseFloat(s);
        return isNaN(n) ? 0 : n;
    };

    // Materiality is set as a % of turnover, not a flat cash figure, so it
    // scales sensibly across clients of very different sizes. Turnover is
    // read from whichever TB row looks like Sales/Turnover/Revenue.
    const computeRevenueBase = () => {
        return tbDataRaw
            .filter(row => /sales|turnover|revenue/i.test(row.account || ""))
            .reduce((sum, row) => sum + Math.abs(parseBalance(row.balance)), 0);
    };

    const computeGlobalMaterialityCash = () => {
        const pct = parseFloat(document.getElementById("input-global-mat").value) || 0;
        const revenueBase = computeRevenueBase();
        if (revenueBase <= 0) {
            // No turnover line found in this batch of the TB (or a nil-revenue
            // client) — fall back to a conservative flat default instead of
            // zeroing out every materiality check.
            return 1000;
        }
        return revenueBase * (pct / 100);
    };

    const updateMaterialityPreview = () => {
        const note = document.getElementById("computed-mat-note");
        if (!note) return;
        const revenueBase = computeRevenueBase();
        const cash = computeGlobalMaterialityCash();
        note.innerText = revenueBase > 0
            ? `= £${cash.toLocaleString(undefined, {maximumFractionDigits: 0})} (turnover £${revenueBase.toLocaleString(undefined, {maximumFractionDigits: 0})})`
            : `= £${cash.toLocaleString(undefined, {maximumFractionDigits: 0})} (no turnover line found yet — using flat fallback)`;
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
        })
            .then(res => { if (!res.ok) throw new Error(`HTTP ${res.status}`); })
            .catch(err => addThought("Critical", `Draft save failed — your progress may not be saved: ${err.message}`, "error"));
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

    // Rebuilds the TB rows list from tbDataRaw applying the current
    // search term / hide-zero-balances toggle, and updates the row count.
    const renderTbRows = () => {
        const rowsCont = document.getElementById("tb-rows");
        const countEl = document.getElementById("tb-row-count");
        rowsCont.innerHTML = "";

        const term = tbSearchTerm.trim().toLowerCase();
        const filtered = tbDataRaw.filter(row => {
            if (hideZeroBalances && parseBalance(row.balance) === 0) return false;
            if (term && !`${row.code} ${row.account}`.toLowerCase().includes(term)) return false;
            return true;
        });

        if (filtered.length === 0) {
            rowsCont.innerHTML = `<div class="flex flex-col items-center justify-center p-16 text-center"><p class="text-secondary font-bold uppercase tracking-[0.2em] text-sm">No nominals match the current filters.</p></div>`;
        } else {
            filtered.forEach(row => {
                const rel = document.createElement("div");
                rel.className = "grid grid-cols-[80px_1fr_100px_100px_100px_100px] gap-4 items-center px-8 py-4 border-b border-border-hairline hover:bg-neutral bg-surface";
                rel.innerHTML = `<div class="font-mono text-[11px] font-bold text-on-surface-muted/70">${row.code}</div><div class="text-on-surface text-[12px] font-bold uppercase">${row.account}</div><div class="text-right font-mono text-[11px]">${row.prev_balance}</div><div class="text-right font-mono text-[11px]">${row.debit}</div><div class="text-right font-mono text-[11px]">${row.credit}</div><div class="text-right font-mono font-bold text-on-surface">${row.balance}</div>`;
                rowsCont.appendChild(rel);
            });
        }

        if (countEl) countEl.innerText = `${filtered.length} / ${tbDataRaw.length} nominals`;
    };

    fetch(`/api/workbench/fetch_tb/${CONFIG.tenantId}?current_year_end=${CONFIG.currentYearEnd}&comparison_year_end=${CONFIG.comparisonYearEnd}`)
        .then(res => res.json())
        .then(data => {
            if (data.status !== "Success") { addThought("Critical", data.message, "error"); return; }
            document.getElementById("tb-loading").remove();
            tbDataRaw = data.tb_raw;
            const coaCont = document.getElementById("coa-cards");

            data.tb_raw.forEach(row => {
                // COA Row - Generated with drill-down container
                const celWrapper = document.createElement("div");
                celWrapper.className = "flex flex-col border-b border-border-hairline";

                const safeId = row.account.replace(/\s+/g, '-');
                const cel = document.createElement("div");
                cel.id = `coa-row-${safeId}`;
                cel.className = "coa-row grid grid-cols-[auto_80px_1fr_100px_100px_200px_72px] gap-4 items-center px-8 py-5 hover:bg-neutral transition-all";
                cel.innerHTML = `<div><input type="checkbox" name="selected_nominal_codes" value="${row.account}" class="coa-check w-5 h-5 text-primary rounded-md border-border-hairline" form="final-form"></div><div class="font-mono text-[11px] font-bold text-on-surface-muted/70">${row.code}</div><p class="text-on-surface text-[13px] font-extrabold uppercase">${row.account}</p><div class="text-right font-mono text-[12px]">${row.prev_balance}</div><div class="text-right font-mono text-[12px] text-on-surface font-bold">${row.balance}</div><div class="rec-cell text-right text-[9px] font-bold text-on-surface-muted uppercase tracking-widest font-mono">Awaiting Scan</div><div class="flex items-center justify-center gap-1"><button type="button" class="btn-notes text-on-surface-muted hover:text-secondary transition-colors" title="Add a note for the AI reviewer"><i data-lucide="sticky-note" class="w-4 h-4"></i></button><button type="button" class="btn-drilldown hidden text-on-surface-muted hover:text-secondary transition-colors"><i data-lucide="chevron-right" class="w-4 h-4"></i></button></div>`;

                const notesPanel = document.createElement("div");
                notesPanel.id = `notes-${safeId}`;
                notesPanel.className = "hidden bg-neutral/40 px-10 py-4 border-t border-border-hairline flex flex-col gap-3";
                notesPanel.innerHTML = `<label class="font-mono text-[10px] uppercase tracking-[0.2em] text-on-surface-muted">Accountant Note</label><textarea class="note-input w-full min-h-[72px] bg-surface border border-border-hairline rounded-md p-3 text-[12px] font-medium text-on-surface focus:outline-none focus:border-primary" placeholder="Add context for the AI reviewer, e.g. 'One-off bonus approved by the board, not expected to recur.'"></textarea><div class="flex justify-end"><button type="button" class="btn-save-note h-9 px-4 font-mono text-[10px] uppercase tracking-[0.14em] bg-secondary text-on-inverse hover:bg-secondary-hover transition-all rounded-full flex items-center gap-2"><i data-lucide="check" class="w-3.5 h-3.5"></i>Save &amp; Re-analyze</button></div>`;

                const drilldown = document.createElement("div");
                drilldown.id = `drilldown-${safeId}`;
                drilldown.className = "hidden bg-neutral/60 px-10 py-4";
                drilldown.innerHTML = `<div class="font-mono text-[10px] uppercase text-on-surface-muted tracking-widest mb-3">Live Transaction Stream (Current Year)</div><div class="tx-list flex flex-col gap-2"></div>`;

                celWrapper.appendChild(cel);
                celWrapper.appendChild(notesPanel);
                celWrapper.appendChild(drilldown);
                coaCont.appendChild(celWrapper);

                const notesBtn = cel.querySelector(".btn-notes");
                const noteInput = notesPanel.querySelector(".note-input");
                notesBtn.addEventListener("click", () => {
                    notesPanel.classList.toggle("hidden");
                    if (!notesPanel.classList.contains("hidden")) noteInput.focus();
                });
                notesPanel.querySelector(".btn-save-note").addEventListener("click", () => {
                    notesMap[row.account] = noteInput.value.trim();
                    notesBtn.classList.toggle("text-secondary", !!notesMap[row.account]);
                    // reRunAccount persists the draft itself once the AI responds,
                    // now carrying the note through since draftMap[account].note
                    // is set from what the backend echoes back.
                    reRunAccount(row.account, row.code, cel.querySelector(".rec-cell"));
                });

                // If we have draft state for this row, apply it immediately
                if (draftMap[row.account]) {
                    const s = draftMap[row.account];
                    applySuggestionToRow(s, row.account, row.code);
                    if (s.note) {
                        notesMap[row.account] = s.note;
                        noteInput.value = s.note;
                        notesBtn.classList.add("text-secondary");
                    }
                }
            });
            renderTbRows();
            addThought("Insight", `Synchronized ${data.tb_raw.length} identities.`, "success");
            refreshIcons();
        });

    document.getElementById("tb-search").addEventListener("input", (e) => {
        tbSearchTerm = e.target.value;
        document.getElementById("btn-clear-filters").classList.toggle("hidden", !tbSearchTerm && !hideZeroBalances);
        renderTbRows();
    });

    document.getElementById("btn-hide-zero").addEventListener("click", (e) => {
        hideZeroBalances = !hideZeroBalances;
        const btn = e.currentTarget;
        btn.classList.toggle("bg-primary", hideZeroBalances);
        btn.classList.toggle("border-primary", hideZeroBalances);
        btn.classList.toggle("bg-surface", !hideZeroBalances);
        btn.innerHTML = hideZeroBalances
            ? `<i data-lucide="eye" class="w-4 h-4"></i>Show Zero Nominals`
            : `<i data-lucide="eye-off" class="w-4 h-4"></i>Hide Zero Nominals`;
        document.getElementById("btn-clear-filters").classList.toggle("hidden", !tbSearchTerm && !hideZeroBalances);
        refreshIcons();
        renderTbRows();
    });

    document.getElementById("btn-clear-filters").addEventListener("click", (e) => {
        tbSearchTerm = "";
        hideZeroBalances = false;
        document.getElementById("tb-search").value = "";
        const hideBtn = document.getElementById("btn-hide-zero");
        hideBtn.classList.remove("bg-primary", "border-primary");
        hideBtn.classList.add("bg-surface");
        hideBtn.innerHTML = `<i data-lucide="eye-off" class="w-4 h-4"></i>Hide Zero Nominals`;
        e.currentTarget.classList.add("hidden");
        refreshIcons();
        renderTbRows();
    });

    const loadTransactions = async (accountCode, accountName, txListContainer) => {
        txListContainer.innerHTML = `<div class="font-mono text-[10px] text-on-surface-muted uppercase tracking-widest animate-pulse py-4">Fetching live data from ledger...</div>`;
        try {
            const nominalMat = document.getElementById("input-nominal-mat").value;
            const res = await fetch(`/api/workbench/nominal_transactions/${CONFIG.tenantId}?account_code=${encodeURIComponent(accountCode || '')}&account_name=${encodeURIComponent(accountName || '')}&current_year_end=${CONFIG.currentYearEnd}&global_materiality=${computeGlobalMaterialityCash()}&nominal_materiality=${encodeURIComponent(nominalMat)}`);
            const data = await res.json();
            txListContainer.innerHTML = "";
            if (data.status === "Success") {
                if (!data.transactions || data.transactions.length === 0) {
                    txListContainer.innerHTML = `<div class="text-xs text-on-surface-muted italic py-2">No material transactions identified.</div>`;
                    return;
                }
                data.transactions.forEach(tx => {
                    const txEl = document.createElement("div");
                    txEl.className = "flex justify-between items-center bg-surface p-3 rounded-md border border-border-hairline";
                    const isSub = (tx.desc && tx.desc.toLowerCase().includes("sub")) ? true : false;
                    const badgeClass = isSub ? 'bg-primary/20 text-secondary' : 'bg-secondary/10 text-secondary';
                    const txTypeStr = isSub ? "Subscription" : "Payment";
                    // Reference is only worth showing when it adds something the
                    // description doesn't already say (avoids "X . X" repetition).
                    const showRef = tx.reference && tx.reference !== tx.desc;
                    txEl.innerHTML = `
                        <div class="flex items-center gap-3">
                            <span class="px-2 py-1 text-[8px] font-bold uppercase tracking-wider rounded-full font-mono ${badgeClass}">${txTypeStr}</span>
                            <span class="text-xs font-bold text-on-surface">${tx.desc || 'System Transaction'}</span>
                            ${showRef ? `<span class="text-[10px] text-on-surface-muted font-mono">Ref: ${tx.reference}</span>` : ''}
                            <span class="text-[10px] text-on-surface-muted font-mono">${tx.date}</span>
                        </div>
                        <div class="font-mono font-bold text-xs text-on-surface">£${tx.amount.toFixed(2)}</div>
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

    // One batch call reused by both the initial full-scan pass and a
    // single-account re-run, so re-running never drifts from the original logic.
    const analyzeBatch = async (rows) => {
        const globalMat = computeGlobalMaterialityCash();
        const res = await fetch(`/api/workbench/analyze_scope_batch/${CONFIG.tenantId}`, {
            method: "POST",
            headers: {"Content-Type": "application/json", "X-CSRFToken": CONFIG.csrfToken},
            body: JSON.stringify({ tb_data: rows, global_materiality: globalMat })
        });
        const result = await res.json();
        if (result.status === "Success" && result.data && result.data.coa_suggestions) {
            return result.data.coa_suggestions;
        }
        throw new Error(result.message || "Analysis failed");
    };

    const reRunAccount = async (accountName, accountCode, rec) => {
        const rowData = tbDataRaw.find(r => r.account === accountName);
        if (!rowData) return;
        rec.innerHTML = `<span class="text-on-surface-muted animate-pulse">Re-scanning…</span>`;
        try {
            const suggestions = await analyzeBatch([{ ...rowData, note: notesMap[accountName] || "" }]);
            const s = suggestions.find(x => x.account === accountName) || suggestions[0];
            if (s) {
                draftMap[accountName] = s;
                const idx = allSuggestions.findIndex(x => x.account === accountName);
                if (idx >= 0) allSuggestions[idx] = s; else allSuggestions.push(s);
                applySuggestionToRow(s, accountName, accountCode);
                saveDraft();
                addThought("System", `Re-ran analysis for "${accountName}".`, "success");
            }
        } catch (err) {
            rec.innerHTML = `<span class="text-error">Re-run failed</span>`;
            addThought("Critical", `Re-run failed for "${accountName}": ${err.message}`, "error");
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
            rec.innerHTML = `<span class="${s.should_analyze ? 'text-error' : 'text-on-surface-muted/60'}">${s.should_analyze ? 'Analyze' : 'Skip'}</span><p class="normal-case text-[8px] text-on-surface-muted tracking-normal mt-1 leading-tight">${s.reason}</p><button type="button" class="btn-rerun normal-case text-[8px] text-secondary hover:text-primary-pressed tracking-normal mt-1 underline">Re-run</button>`;
            rec.querySelector(".btn-rerun").addEventListener("click", (e) => {
                e.stopPropagation();
                reRunAccount(accountName, accountCode, rec);
            });

            if (s.should_analyze) {
                // Highlight row
                row.classList.add("bg-error/5");
                row.classList.remove("opacity-50");

                // Always show drilldown for analyzed
                arrowBtn.classList.remove("hidden");
                // Remove existing listeners if any by cloning
                const newBtn = arrowBtn.cloneNode(true);
                arrowBtn.parentNode.replaceChild(newBtn, arrowBtn);

                newBtn.addEventListener("click", () => {
                    drilldown.classList.toggle("hidden");
                    const isOpen = !drilldown.classList.contains("hidden");
                    newBtn.innerHTML = `<i data-lucide="${isOpen ? 'chevron-down' : 'chevron-right'}" class="w-4 h-4"></i>`;
                    refreshIcons();

                    // If opening and not loaded yet
                    if (isOpen && txList.innerHTML === "") {
                        loadTransactions(accountCode, accountName, txList);
                    }
                });
            } else {
                row.classList.add("opacity-50");
                row.classList.remove("bg-error/5");
                arrowBtn.classList.add("hidden");
            }
            refreshIcons();
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
        agentDot.className = "h-2 w-2 rounded-full bg-primary animate-pulse";

        const batchSize = 10;

        for (let i = 0; i < unanalyzed.length; i += batchSize) {
            const batch = unanalyzed.slice(i, i + batchSize).map(r => ({ ...r, note: notesMap[r.account] || "" }));
            addThought("System", `Processing batch ${Math.floor(i/batchSize)+1}...`, "info");

            try {
                const suggestions = await analyzeBatch(batch);
                suggestions.forEach(s => {
                    // Store the suggestion
                    draftMap[s.account] = s;
                    allSuggestions.push(s);

                    applySuggestionToRow(s, s.account, s.code);
                });
                // Save draft after each successful batch
                saveDraft();
            } catch (err) {
                console.error(err);
                addThought("Critical", `Batch ${Math.floor(i/batchSize)+1} failed: ${err.message}`, "error");
            }
        }

        addThought("System", "Batch AI analysis completed. Workspace saved as DRAFT.", "success");
        statusText.innerText = "Live Scan";
        agentDot.className = "h-2 w-2 rounded-full bg-primary";
    };

    // Navigation & Modals
    document.getElementById("btn-to-coa").addEventListener("click", () => {
        setTbFullscreen(false);
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
        updateMaterialityPreview();
    });

    document.getElementById("input-global-mat").addEventListener("input", updateMaterialityPreview);

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
        setCoaFullscreen(false);
        const checked = document.querySelectorAll(".coa-check:checked");
        document.getElementById("analysis-total").innerText = checked.length;
        document.getElementById("analysis-empty-state").classList.add("hidden");
        activePill(3);
        transitionTo(stageCoa, stageAnalysis, 300);

        let i = 0;
        checked.forEach(c => {
            setTimeout(() => {
                const card = document.createElement("div");
                card.className = "bg-surface p-6 border border-border-hairline rounded-lg shadow-ambient flex items-center gap-4";
                card.innerHTML = `<i data-lucide="check-circle" class="w-5 h-5 text-success"></i><p class="text-on-surface font-bold uppercase text-xs">${c.value}</p><span class="font-mono text-[9px] text-on-surface-muted ml-auto uppercase font-bold">Ready for Crew</span>`;
                document.getElementById("analysis-cards").appendChild(card);
                refreshIcons();
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
