import os
import json
import logging
import threading
import uuid
from typing import Dict, Any
from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField
from wtforms.validators import DataRequired, NumberRange
from flask_login import login_required, current_user
from strings.paths import NL_PATH, TB_PATH, TRANS_PATH, FILE_PATH_OUT
from strings.assistant import DEPLOYED_MODEL_NAME
from helpers.data_processors import xero_info_to_message
from helpers.mappers import xero_iris_mapper
from helpers.utility import save_systematic_output, save_uploaded_file
from setup.app_factory import create_app
import dotenv

dotenv.load_dotenv()

# set cwd to the current directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

app = create_app()

from routes.auth_routes import auth_bp
app.register_blueprint(auth_bp)

class UploadForm(FlaskForm):
    pass

class ExperimentForm(FlaskForm):
    run_name = StringField("Run name", validators=[DataRequired()])
    dataset_limit = IntegerField(
        "Examples (limit)", default=10, validators=[DataRequired(), NumberRange(min=1, max=6000)]
    )
    dataset_offset = IntegerField(
        "Offset", default=0, validators=[DataRequired(), NumberRange(min=0, max=6000)]
    )
    examples_prefix = StringField("Blob prefix override", default="")
    few_shot_k = IntegerField(
        "Few-shot K", default=3, validators=[DataRequired(), NumberRange(min=0, max=10)]
    )
    prompt_search_trials = IntegerField(
        "Prompt trials", default=8, validators=[DataRequired(), NumberRange(min=1, max=50)]
    )

def run_analysis_thread(tenant_id: str, user_id: int, selected_nominal_codes: list = None, run_id: str = None, current_year_end: str = None, comparison_year_end: str = None):
    """Background task to run the main process using APIs, logging to an event stream."""
    import time
    from setup.models import User
    from integrations.xero_api import XeroClient
    from datetime import date

    
    # Setup Event Log
    log_file_path = os.path.join(app.config["UPLOAD_FOLDER"], f"{run_id}.jsonl")
    def emit_event(event_type, **kwargs):
        event = {"type": event_type, "timestamp": time.time()}
        event.update(kwargs)
        with open(log_file_path, "a") as f:
            f.write(json.dumps(event) + "\n")

    emit_event("start", message="Analysis starting...")

    with app.app_context():
        try:
            user = User.query.get(user_id)
            token_data = user.get_xero_token()
            if not token_data:
                emit_event("error", logic="No Xero token associated with user")
                return
            xero_client = XeroClient(
                client_id=os.environ.get("XERO_CLIENT_ID"),
                client_secret=os.environ.get("XERO_CLIENT_SECRET"),
                refresh_token=token_data.get("refresh_token"),
                user=user
            )
            
            emit_event("progress", message="Fetching Trial Balance and executing Xero mappings...")
            report_date = date.fromisoformat(current_year_end) if current_year_end else date.today()
            comparison_date = date.fromisoformat(comparison_year_end) if comparison_year_end else None
            
            from helpers.xero_api_parser import fetch_and_format_xero_data
            messages, mp_df = fetch_and_format_xero_data(xero_client, tenant_id, report_date, comparison_date=comparison_date)
            
            if selected_nominal_codes is not None:
                messages = [m for m in messages if m["name"] in selected_nominal_codes]
                
            emit_event("progress", message=f"Mapped {len(messages)} focus targets. Starting synthesis...")
            
            from main_crew import run_all_crew
            run_all_crew(
                messages,
                mp_df,
                FILE_PATH_OUT=FILE_PATH_OUT,
                emit_event=emit_event
            )
            
            # Save to Database History
            try:
                # Get tenant name for history
                connections = xero_client.list_connections()
                t_name = "Unknown Client"
                for c in connections:
                    if c['tenantId'] == tenant_id:
                        t_name = c['tenantName']
                        break
                
                from setup.models import db, ReviewNote
                new_note = ReviewNote(
                    user_id=user_id,
                    tenant_id=tenant_id,
                    tenant_name=t_name,
                    run_id=run_id,
                    year_start=str(comparison_date) if comparison_date else "N/A",
                    year_end=str(report_date),
                    status='COMPLETED'
                )
                db.session.add(new_note)
                db.session.commit()
            except Exception as db_err:
                logging.error(f"Failed to save history: {str(db_err)}")

            emit_event("complete", message="Core analysis successfully completed.", result_file=FILE_PATH_OUT)
        except Exception as e:
            emit_event("error", logic=str(e))

def async_run_experiment(run_def_payload: dict) -> Dict[str, Any]:
    # (Leaving experiment task exactly as is)
    try:
        from experiments.config import load_config
        from experiments.example_loader import (
            load_examples_from_blob,
            load_examples_from_local_dir,
            enrich_examples_from_xero_api,
        )
        from experiments.models import ModelRegistry
        from experiments.orchestrator import run_experiment
        from experiments.storage import ExampleCache
        from experiments.store import SqliteExperimentStore
        from experiments.types import (
            MaterialityPolicy,
            ModelSpec,
            RunDefinition,
            ScoringConfig,
            SubscriptionPolicy,
        )

        cfg = load_config()
        cache = ExampleCache(cfg.cache_dir)
        store = SqliteExperimentStore(cfg.store_path)
        registry = ModelRegistry(cfg)

        models = [
            ModelSpec(
                model_id=m["model_id"],
                provider=m["provider"],
                config=m.get("config", {}),
            )
            for m in run_def_payload["models"]
        ]

        run_def = RunDefinition(
            run_name=run_def_payload["run_name"],
            models=models,
            techniques=run_def_payload["techniques"],
            context_modes=run_def_payload["context_modes"],
            dataset_limit=int(run_def_payload.get("dataset_limit", 25)),
            dataset_offset=int(run_def_payload.get("dataset_offset", 0)),
            examples_prefix=str(run_def_payload.get("examples_prefix", "") or ""),
            materiality_policy=MaterialityPolicy(**run_def_payload.get("materiality_policy", {})),
            subscription_policy=SubscriptionPolicy(**run_def_payload.get("subscription_policy", {})),
            scoring=ScoringConfig(**run_def_payload.get("scoring", {})),
            few_shot_k=int(run_def_payload.get("few_shot_k", 3)),
            prompt_search_trials=int(run_def_payload.get("prompt_search_trials", 12)),
            prompt_search_dev_size=int(run_def_payload.get("prompt_search_dev_size", 8)),
        )

        examples_local_dir = os.environ.get("EXAMPLES_LOCAL_DIR")
        if examples_local_dir:
            examples = load_examples_from_local_dir(
                directory=examples_local_dir,
                limit=run_def.dataset_limit,
                offset=run_def.dataset_offset,
            )
        else:
            examples = load_examples_from_blob(
                blob=cfg.blob,
                cache=cache,
                limit=run_def.dataset_limit,
                offset=run_def.dataset_offset,
                prefix_override=run_def.examples_prefix or None,
            )

        if os.environ.get("EXAMPLES_ENRICH_FROM_XERO_API", "").strip() in ("1", "true", "TRUE", "yes", "YES"):
            examples = enrich_examples_from_xero_api(examples)

        run_id = run_experiment(
            run_def=run_def,
            examples=examples,
            store=store,
            model_registry=registry,
        )
        return {"status": "Task completed", "run_id": run_id}
    except Exception as e:
        return {"status": "Error", "message": str(e)}

def _available_models():
    models = []

    dep_primary = os.environ.get("EXPERIMENT_AZURE_DEPLOYMENT_PRIMARY") or DEPLOYED_MODEL_NAME
    dep_secondary = os.environ.get("EXPERIMENT_AZURE_DEPLOYMENT_SECONDARY", "").strip()

    if dep_primary:
        models.append(
            {
                "key": f"azure:{dep_primary}",
                "spec": {
                    "model_id": f"azure:{dep_primary}",
                    "provider": "azure_openai",
                    "config": {"deployment_name": dep_primary},
                },
                "label": f"Azure OpenAI: {dep_primary}",
            }
        )
    if dep_secondary:
        models.append(
            {
                "key": f"azure:{dep_secondary}",
                "spec": {
                    "model_id": f"azure:{dep_secondary}",
                    "provider": "azure_openai",
                    "config": {"deployment_name": dep_secondary},
                },
                "label": f"Azure OpenAI: {dep_secondary}",
            }
        )

    oss_base = os.environ.get("OSS_MODEL_PATH_BASE", "").strip()
    if oss_base:
        models.append(
            {
                "key": "oss:base",
                "spec": {
                    "model_id": "oss:base",
                    "provider": "transformers",
                    "config": {"model_name_or_path": oss_base},
                },
                "label": f"OSS (base): {oss_base}",
            }
        )
    oss_adapter = os.environ.get("OSS_LORA_ADAPTER_PATH", "").strip()
    if oss_base and oss_adapter:
        models.append(
            {
                "key": "oss:lora",
                "spec": {
                    "model_id": "oss:lora",
                    "provider": "transformers",
                    "config": {"model_name_or_path": oss_base, "adapter_path": oss_adapter},
                },
                "label": f"OSS (LoRA): {oss_base} + {oss_adapter}",
            }
        )

    return models

@app.route("/", methods=["GET", "POST"])
@login_required
def upload():
    """Dashboard showing connected clients and handling analysis initiation."""
    connections = []
    has_xero_token = current_user.get_xero_token() is not None
    
    if request.method == "POST":
        tenant_id = request.form.get("tenant_id")
        current_year_end = request.form.get("current_year_end")
        comparison_year_end = request.form.get("comparison_year_end")
        selected_nominal_codes = request.form.getlist("selected_nominal_codes")

        if not tenant_id:
            flash("Mandate missing. Please retry.")
            return redirect(url_for('upload'))
            
        run_id = str(uuid.uuid4())
        
        # Clean up any existing DRAFT for this tenant
        from setup.models import db, ReviewNote
        draft = ReviewNote.query.filter_by(user_id=current_user.id, tenant_id=tenant_id, status="DRAFT").first()
        if draft:
            db.session.delete(draft)
            db.session.commit()
            
        thread = threading.Thread(
            target=run_analysis_thread,
            args=(tenant_id, current_user.id, selected_nominal_codes, run_id, current_year_end, comparison_year_end)
        )
        thread.start()
        return redirect(url_for("report_stream", run_id=run_id))

    if has_xero_token:
        try:
            from integrations.xero_api import XeroClient
            token_data = current_user.get_xero_token()
            xero_client = XeroClient(
                client_id=os.environ.get("XERO_CLIENT_ID"),
                client_secret=os.environ.get("XERO_CLIENT_SECRET"),
                refresh_token=token_data.get("refresh_token"),
                user=current_user
            )
            connections = xero_client.list_connections()
        except Exception as e:
            flash(f"Could not load Xero connections: {str(e)}")
            has_xero_token = False

    return render_template("index.html", connections=connections, has_xero_token=has_xero_token)


@app.route("/client/<tenant_id>")
@login_required
def client_detail(tenant_id):
    """Specific client mandate overview."""
    from setup.models import ReviewNote
    from integrations.xero_api import XeroClient
    
    token_data = current_user.get_xero_token()
    if not token_data:
        flash("Authorization required.")
        return redirect(url_for('upload'))
        
    xero_client = XeroClient(
        client_id=os.environ.get("XERO_CLIENT_ID"),
        client_secret=os.environ.get("XERO_CLIENT_SECRET"),
        refresh_token=token_data.get("refresh_token"),
        user=current_user
    )
    
    # Discovery of specific tenant name
    connections = xero_client.list_connections()
    tenant_name = "Unknown Client"
    for conn in connections:
        if conn['tenantId'] == tenant_id:
            tenant_name = conn['tenantName']
            break
            
    # Fetch previous notes for this tenant
    history = ReviewNote.query.filter_by(user_id=current_user.id, tenant_id=tenant_id).order_by(ReviewNote.created_at.desc()).all()
    
    return render_template("client_detail.html", 
        tenant_id=tenant_id, 
        tenant_name=tenant_name,
        history=history
    )


@app.route("/workbench", methods=["POST"])
@login_required
def workbench():
    tenant_id = request.form.get("tenant_id")
    current_year_end = request.form.get("current_year_end")
    comparison_year_end = request.form.get("comparison_year_end")

    if not tenant_id:
        flash("Please select a Xero tenant before accessing the workbench.")
        return redirect(url_for("upload"))
        
    return render_template("workbench.html", 
        tenant_id=tenant_id, 
        current_year_end=current_year_end, 
        comparison_year_end=comparison_year_end
    )


@app.route("/api/workbench/fetch_tb/<tenant_id>", methods=["GET"])
@login_required
def fetch_tb(tenant_id):
    from integrations.xero_api import XeroClient
    from datetime import date
    
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
        
        current_date_str = request.args.get('current_year_end')
        report_date = date.fromisoformat(current_date_str) if current_date_str else date.today()
        from dateutil.relativedelta import relativedelta
        prev_report_date = report_date - relativedelta(years=1)

        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(xero_client.get_trial_balance, tenant_id, report_date=report_date)
            f2 = executor.submit(xero_client.get_trial_balance, tenant_id, report_date=prev_report_date)
            tb_json = f1.result()
            prev_tb_json = f2.result()

        def extract_tb_rows(rows, target_dict):
            for r in rows:
                if r.get("RowType") == "Row":
                    cells = r.get("Cells", [])
                    if cells and len(cells) > 0 and cells[0].get("Value") != "Total":
                        target_dict[cells[0].get("Value")] = cells
                elif "Rows" in r:
                    extract_tb_rows(r["Rows"], target_dict)

        tb_dict = {}
        prev_tb_dict = {}
        if tb_json.get("Reports"):
            extract_tb_rows(tb_json["Reports"][0].get("Rows", []), tb_dict)
        if prev_tb_json.get("Reports"):
            extract_tb_rows(prev_tb_json["Reports"][0].get("Rows", []), prev_tb_dict)

        tb_raw_data = []
        for acc_name, cells in tb_dict.items():
            debit = cells[1].get("Value", "0") if len(cells) > 1 else "0"
            credit = cells[2].get("Value", "0") if len(cells) > 2 else "0"
            prev_cells = prev_tb_dict.get(acc_name, [])
            prev_balance = prev_cells[1].get("Value", "0") if len(prev_cells) > 1 else "0"
            balance = cells[1].get("Value", "") if len(cells) > 1 else ""
            
            tb_raw_data.append({
                "account": acc_name,
                "code": acc_name.split("-")[0].strip() if "-" in acc_name else "",
                "debit": debit,
                "credit": credit,
                "balance": balance,
                "prev_balance": prev_balance
            })

        return jsonify({"status": "Success", "tb_raw": tb_raw_data})
    except Exception as e:
        return jsonify({"status": "Error", "message": str(e)}), 500


@app.route("/api/workbench/analyze_scope_batch/<tenant_id>", methods=["POST"])
@login_required
def analyze_scope_batch(tenant_id):
    from helpers.batch_analyzer import analyze_nominal_batch
    tb_data = request.json.get("tb_data", [])
    global_mat = request.json.get("global_materiality", 1000)
    
    try:
        results = analyze_nominal_batch(tb_data, float(global_mat))
        return jsonify({"status": "Success", "data": {"coa_suggestions": results}})
    except Exception as e:
        return jsonify({"status": "Error", "message": str(e)}), 500


@app.route("/api/workbench/save_draft/<tenant_id>", methods=["POST"])
@login_required
def save_draft(tenant_id):
    from setup.models import db, ReviewNote
    import uuid, json, os
    from flask import current_app
    
    current_year_end = request.json.get("current_year_end")
    comparison_year_end = request.json.get("comparison_year_end")
    draft_state = request.json.get("draft_state", [])
    
    draft = ReviewNote.query.filter_by(user_id=current_user.id, tenant_id=tenant_id, status="DRAFT").first()
    if not draft:
        draft = ReviewNote(
            user_id=current_user.id,
            tenant_id=tenant_id,
            run_id=f"draft_{uuid.uuid4().hex[:8]}",
            status="DRAFT",
            year_end=current_year_end,
            year_start=comparison_year_end
        )
        db.session.add(draft)
        db.session.commit()
    
    # Save the draft state to a file
    draft_file = os.path.join(current_app.config["UPLOAD_FOLDER"], f"{draft.run_id}_draft.json")
    with open(draft_file, 'w') as f:
        json.dump(draft_state, f)
        
    return jsonify({"status": "Success", "message": "Draft saved"})

@app.route("/api/workbench/load_draft/<tenant_id>", methods=["GET"])
@login_required
def load_draft(tenant_id):
    from setup.models import ReviewNote
    import os, json
    from flask import current_app
    
    draft = ReviewNote.query.filter_by(user_id=current_user.id, tenant_id=tenant_id, status="DRAFT").first()
    if draft:
        draft_file = os.path.join(current_app.config["UPLOAD_FOLDER"], f"{draft.run_id}_draft.json")
        if os.path.exists(draft_file):
            with open(draft_file, 'r') as f:
                draft_state = json.load(f)
            return jsonify({"status": "Success", "draft_state": draft_state, "current_year_end": draft.year_end, "comparison_year_end": draft.year_start})
            
    return jsonify({"status": "NotFound"})


@app.route("/api/workbench/nominal_transactions/<tenant_id>", methods=["GET"])
@login_required
def nominal_transactions(tenant_id):
    from integrations.xero_api import XeroClient
    from datetime import date
    from dateutil.relativedelta import relativedelta
    import traceback

    account_code = request.args.get("account_code")
    account_name = request.args.get("account_name")
    current_year_end = request.args.get("current_year_end")
    if not current_year_end or (not account_code and not account_name):
        return jsonify({"status": "Error", "message": "Missing parameter"}), 400

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
            if account_code and acc.get("Code") == account_code:
                account_id = acc.get("AccountID")
                break
            elif account_name and acc.get("Name") == account_name:
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


@app.route("/api/workbench/prime_ledger/<tenant_id>", methods=["GET"])
@login_required
def prime_ledger(tenant_id):
    from integrations.xero_api import XeroClient
    from datetime import date, timedelta
    from dateutil.relativedelta import relativedelta

    token_data = current_user.get_xero_token()
    if not token_data:
        return jsonify({"status": "Error", "message": "No Xero token"}), 400

    try:
        current_date_str = request.args.get('current_year_end')
        report_date = date.fromisoformat(current_date_str) if current_date_str else date.today()
    except ValueError:
        report_date = date.today()

    start_date = report_date - relativedelta(years=1) + timedelta(days=1)
    prev_report_date = report_date - relativedelta(years=1)
    prev_start_date = prev_report_date - relativedelta(years=1) + timedelta(days=1)

    try:
        xero_client = XeroClient(
            client_id=os.environ.get("XERO_CLIENT_ID"),
            client_secret=os.environ.get("XERO_CLIENT_SECRET"),
            refresh_token=token_data.get("refresh_token"),
            user=current_user
        )
        
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=4) as executor:
            # Trigger broad fetches to populate global cache in parallel
            executor.submit(xero_client.get_bank_transactions, tenant_id, start_date=start_date, end_date=report_date)
            executor.submit(xero_client.get_invoices, tenant_id, start_date=start_date, end_date=report_date, statuses=["AUTHORISED", "PAID"])
            executor.submit(xero_client.get_bank_transactions, tenant_id, start_date=prev_start_date, end_date=prev_report_date)
            executor.submit(xero_client.get_invoices, tenant_id, start_date=prev_start_date, end_date=prev_report_date, statuses=["AUTHORISED", "PAID"])

        return jsonify({"status": "Success", "message": "Ledger cache primed."})
    except Exception as e:
        return jsonify({"status": "Error", "message": str(e)}), 500

@app.route("/api/workbench/analyze_nominal/<tenant_id>", methods=["GET"])
@login_required
def analyze_nominal(tenant_id):
    from integrations.xero_api import XeroClient
    from datetime import date, timedelta
    from dateutil.relativedelta import relativedelta
    import json
    import os
    from openai import AzureOpenAI
    from strings.assistant import API_VERSION, DEPLOYED_MODEL_NAME
    
    token_data = current_user.get_xero_token()
    if not token_data:
        return jsonify({"status": "Error", "message": "No Xero token"}), 400
        
    nominal_name = request.args.get('nominal')
    account_id = request.args.get('account_id')
    
    if not nominal_name:
        return jsonify({"status": "Error", "message": "No nominal name provided"}), 400
        
    try:
        xero_client = XeroClient(
            client_id=os.environ.get("XERO_CLIENT_ID"),
            client_secret=os.environ.get("XERO_CLIENT_SECRET"),
            refresh_token=token_data.get("refresh_token"),
            user=current_user
        )
        
        # 1. Resolve Account details (especially the Code for filtering)
        accounts = xero_client.get_accounts(tenant_id).get("Accounts", [])
        target_account = None

        if account_id and account_id != "undefined" and account_id != "null":
            # Search by ID first
            for acc in accounts:
                if acc.get("AccountID") == account_id:
                    target_account = acc
                    break
        
        # Fallback to name/code match if ID not provided or not found
        if not target_account:
            for acc in accounts:
                code = acc.get('Code', '')
                name = acc.get('Name', '')
                full_name = f"{code} - {name}"
                if full_name == nominal_name or name == nominal_name or code == nominal_name:
                    target_account = acc
                    break
            
            if not target_account and nominal_name:
                # Fallback to fuzzy match
                for acc in accounts:
                    code = acc.get('Code', '')
                    name = acc.get('Name', '')
                    if (code and code in nominal_name) and (name and name in nominal_name):
                        target_account = acc
                        break
        
        if not target_account:
            return jsonify({"status": "Error", "message": f"Account details for '{nominal_name}' (ID: {account_id}) not found in Xero."}), 404
            
        account_id = target_account["AccountID"]
        target_code = target_account.get("Code")
        
        # 2. Date ranges
        try:
            current_date_str = request.args.get('current_year_end')
            report_date = date.fromisoformat(current_date_str) if current_date_str else date.today()
        except ValueError:
            report_date = date.today()
            
        start_date = report_date - relativedelta(years=1) + timedelta(days=1)
        prev_report_date = report_date - relativedelta(years=1)
        prev_start_date = prev_report_date - relativedelta(years=1) + timedelta(days=1)
        
        # 3. Fetch Transactions (Bank Transactions and Invoices) for both years
        def fetch_and_filter_transactions(s_date, e_date):
            txs = []
            try:
                # Fetch BROAD (unfiltered by code) to trigger the global cache for subsequent parallel workers
                bt_resp = xero_client.get_bank_transactions(tenant_id, start_date=s_date, end_date=e_date, max_pages=50)
                inv_resp = xero_client.get_invoices(tenant_id, start_date=s_date, end_date=e_date, statuses=["AUTHORISED", "PAID"], max_pages=50)
                
                # Filter in-memory for the target nominal
                # Process Bank Transactions
                for bt in bt_resp.get("BankTransactions", []):
                    for li in bt.get("LineItems", []):
                        if li.get("AccountCode") == target_code:
                            txs.append({
                                "Date": bt.get("DateString", bt.get("Date", "")),
                                "Source": "BankTransaction",
                                "Description": li.get("Description", bt.get("Reference", "")),
                                "Reference": bt.get("Reference", ""),
                                "Contact": bt.get("Contact", {}).get("Name", ""),
                                "Total": li.get("LineAmount", "")
                            })
                            
                # Process Invoices
                for inv in inv_resp.get("Invoices", []):
                    for li in inv.get("LineItems", []):
                        if li.get("AccountCode") == target_code:
                            txs.append({
                                "Date": inv.get("DateString", inv.get("Date", "")),
                                "Source": "Invoice",
                                "Description": li.get("Description", inv.get("InvoiceNumber", "")),
                                "Reference": inv.get("Reference", ""),
                                "Contact": inv.get("Contact", {}).get("Name", ""),
                                "Total": li.get("LineAmount", "")
                            })
            except Exception as e:
                print(f"Error fetching/filtering transactions for {target_code}: {e}")
            return txs

        curr_txs = fetch_and_filter_transactions(start_date, report_date)
        prev_txs = fetch_and_filter_transactions(prev_start_date, prev_report_date)
        
        print(f"DEBUG: {nominal_name} - Current Txs: {len(curr_txs)}, Previous Txs: {len(prev_txs)}")
        
        # 4. AI Analysis for Subscriptions and Outliers
        global_mat = request.args.get('global_materiality', '1000')
        nominal_mat = request.args.get('nominal_materiality', '500')

        client = AzureOpenAI(
            api_key=os.environ.get("AZURE_OPENAI_API_KEY"),
            api_version=API_VERSION,
            azure_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT")
        )
        
        context_str = f"Current Year Transactions ({start_date} to {report_date}) - Total Found: {len(curr_txs)}:\n"
        context_str += "\n".join([str(t) for t in curr_txs[:50]]) # Limit to 50 for tokens
        context_str += f"\n\nPrevious Year Transactions ({prev_start_date} to {prev_report_date}) - Total Found: {len(prev_txs)}:\n"
        context_str += "\n".join([str(t) for t in prev_txs[:50]])
        
        prompt = f"""
You are an expert UK accounting AI. Analyze these transactions for nominal account '{nominal_name}'.
The configured Global Materiality is £{global_mat} and Nominal Materiality (trivial threshold) is £{nominal_mat}.

Identify:
1. Recurring Subscriptions: Payments that occur regularly (monthly/annually) in both years or new in this year.
2. Outlier Payments: Large or unusual payments. Focus on items exceeding Nominal Materiality (£{nominal_mat}). Items exceeding Global Materiality (£{global_mat}) are CRITICAL.
3. Year-on-Year Variances: Notable new vendors or stopped vendors.

Please generate a JSON response:
{{
  "subscriptions": [
    {{"name": "...", "amount": "...", "frequency": "...", "status": "New / Existing / Stopped", "logic": "..."}}
  ],
  "outliers": [
    {{"name": "...", "amount": "...", "date": "...", "logic": "..."}}
  ],
  "summary": "Brief overall transactional insight."
}}
        """
        
        response = client.chat.completions.create(
            model=DEPLOYED_MODEL_NAME,
            messages=[
                {"role": "system", "content": "You are a JSON-producing accounting assistant."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.1
        )
        
        result_data = json.loads(response.choices[0].message.content)
        return jsonify({"status": "Success", "nominal": nominal_name, "data": result_data, "transactions": curr_txs})
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"status": "Error", "message": str(e)}), 500

@app.route("/report/<run_id>")
def report_stream(run_id: str):
    """Serve the realtime report dashboard."""
    return render_template("report_stream.html", run_id=run_id)

@app.route("/api/stream_report/<run_id>")
def stream_report(run_id: str):
    """SSE endpoint for live report streaming."""
    import time
    from flask import Response
    
    log_file_path = os.path.join(app.config["UPLOAD_FOLDER"], f"{run_id}.jsonl")
    
    def generate():
        last_pos = 0
        while True:
            if os.path.exists(log_file_path):
                with open(log_file_path, "r") as f:
                    f.seek(last_pos)
                    lines = f.readlines()
                    last_pos = f.tell()
                    
                    for line in lines:
                        if line.strip():
                            yield f"data: {line}\n\n"
                            try:
                                data = json.loads(line)
                                if data.get("type") in ["complete", "error"]:
                                    return
                            except Exception:
                                pass
            time.sleep(0.5)
            
    return Response(generate(), mimetype="text/event-stream")

@app.route("/revoke/<task_id>")
def revoke_task(task_id: str):
    """Deprecated: Celery has been removed."""
    return jsonify({"task_id": task_id, "status": "Not supported in threading architecture"})


@app.route("/experiments", methods=["GET"])
def experiments_home():
    from experiments.config import load_config
    from experiments.store import SqliteExperimentStore

    cfg = load_config()
    store = SqliteExperimentStore(cfg.store_path)
    runs = store.list_runs(limit=20)

    form = ExperimentForm()
    model_choices = [(m["key"], m["label"]) for m in _available_models()]
    technique_choices = [
        ("zero_shot", "zero_shot"),
        ("prompt_optimised", "prompt_optimised"),
        ("few_shot", "few_shot"),
        ("fine_tuned", "fine_tuned"),
    ]
    context_choices = [
        ("raw", "raw (raw_25/raw_50/raw_100)"),
        ("materiality", "materiality"),
        ("subscriptions", "subscriptions"),
        ("materiality+subscriptions", "materiality+subscriptions"),
    ]

    return render_template(
        "experiments.html",
        form=form,
        runs=runs,
        model_choices=model_choices,
        technique_choices=technique_choices,
        context_choices=context_choices,
        default_context_modes=["raw", "materiality+subscriptions"],
    )


@app.route("/experiments/start", methods=["POST"])
def start_experiment():
    form = ExperimentForm()
    if not form.validate_on_submit():
        flash("Invalid experiment form submission")
        return redirect(url_for("experiments_home"))

    available = {m["key"]: m for m in _available_models()}
    selected_models = request.form.getlist("models")
    techniques = request.form.getlist("techniques")
    context_modes = request.form.getlist("context_modes")

    if not selected_models:
        flash("Select at least one model")
        return redirect(url_for("experiments_home"))
    if not techniques:
        flash("Select at least one technique")
        return redirect(url_for("experiments_home"))
    if not context_modes:
        flash("Select at least one context mode")
        return redirect(url_for("experiments_home"))

    models_payload = [available[k]["spec"] for k in selected_models if k in available]
    run_def_payload = {
        "run_name": form.run_name.data,
        "models": models_payload,
        "techniques": techniques,
        "context_modes": context_modes,
        "dataset_limit": int(form.dataset_limit.data),
        "dataset_offset": int(form.dataset_offset.data),
        "examples_prefix": (form.examples_prefix.data or "").strip(),
        "few_shot_k": int(form.few_shot_k.data),
        "prompt_search_trials": int(form.prompt_search_trials.data),
        "prompt_search_dev_size": min(8, int(form.dataset_limit.data)),
        "materiality_policy": {"relative_fraction": 0.01, "absolute_gbp": None, "base_field": "total"},
        "subscription_policy": {"min_occurrences": 3, "amount_tolerance_gbp": 2.0},
        "scoring": {"require_single_paragraph": True, "forbid_ref_numbers": True},
    }

    task = async_run_experiment.delay(run_def_payload)
    return redirect(url_for("experiment_status", task_id=task.id))


@app.route("/experiments/status/<task_id>")
def experiment_status(task_id: str):
    task = AsyncResult(task_id)
    run_id = None
    if task.state == "PENDING":
        state = task.state
        status = "Experiment is pending..."
        error = None
    elif task.state != "FAILURE":
        state = task.state
        status = task.info.get("status", "")
        run_id = task.info.get("run_id")
        error = task.info.get("message") if task.info.get("status") == "Error" else None
    else:
        state = task.state
        status = "Error occurred"
        error = str(task.info)

    return render_template(
        "experiment_status.html",
        state=state,
        status=status,
        run_id=run_id,
        error=error,
    )


@app.route("/experiments/run/<run_id>")
def experiment_run(run_id: str):
    from experiments.config import load_config
    from experiments.store import SqliteExperimentStore

    cfg = load_config()
    store = SqliteExperimentStore(cfg.store_path)
    run = store.get_run(run_id)
    if not run:
        return "Run not found", 404
    generations = store.list_generations(run_id)
    return render_template(
        "experiment_run.html",
        run=run,
        generations=generations,
    )


@app.route("/experiments/run/<run_id>/download.csv")
def download_run_csv(run_id: str):
    import csv
    import io
    from flask import Response
    from experiments.config import load_config
    from experiments.store import SqliteExperimentStore

    cfg = load_config()
    store = SqliteExperimentStore(cfg.store_path)
    buf = io.StringIO()
    w = csv.writer(buf)
    for row in store.export_generations_csv_rows(run_id):
        w.writerow(row)
    csv_bytes = buf.getvalue().encode("utf-8")
    return Response(
        csv_bytes,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={run_id}.csv"},
    )


@app.route("/experiments/run/<run_id>/download.json")
def download_run_json(run_id: str):
    import json as _json
    from flask import Response
    from experiments.config import load_config
    from experiments.store import SqliteExperimentStore

    cfg = load_config()
    store = SqliteExperimentStore(cfg.store_path)
    payload = {"run": store.get_run(run_id), "generations": store.list_generations(run_id)}
    return Response(
        _json.dumps(payload, ensure_ascii=True, indent=2).encode("utf-8"),
        mimetype="application/json",
        headers={"Content-Disposition": f"attachment; filename={run_id}.json"},
    )

@app.route("/api/send_report/<run_id>", methods=["POST"])
@login_required
def send_report(run_id: str):
    email = request.json.get("email")
    if not email:
        return jsonify({"status": "error", "message": "No email provided"}), 400
        
    try:
        from helpers.email_service import send_email
        from strings.paths import FILE_PATH_OUT
        subject = "Report for the Generated Reviews | PHM Accountants"
        body = f"""Hello,
        
Please find the attached report for the generated reviews. 

The report contains the generated reviews for the accounts in the trial balance, based directly on live Xero APIs. 

The link to the generated reviews is as follows: https://ai.phm-accountants.co.uk/result/

Regards,
Technical Team,
PHM Accountants
"""
        recipient_list = [
            {"address": f"{email}", "displayName": "PHM Accountant"},
        ]
        sender_address = "donotreply@e444ea86-37e7-4a7d-857b-261cf490d7ce.azurecomm.net"

        # Usually you'd send FILE_PATH_OUT but to be robust to concurrent runs, we'll just send standard path for now
        # send email via azure
        from integrations.azure_email import send_email_with_attachment
        send_email_with_attachment(
            subject=subject,
            body=body,
            recipient_list=recipient_list,
            sender_address=sender_address,
            file_path=FILE_PATH_OUT,
        )
        return jsonify({"status": "success", "message": "Email sent successfully."})
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    with app.app_context():
        from setup.models import db
        db.create_all()
    app.run(host="0.0.0.0", port=5000, debug=True)
