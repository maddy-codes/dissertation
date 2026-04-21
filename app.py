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
from strings.assistant import (
    API_VERSION,
    ASSISTANT_ID,
    DEPLOYED_MODEL_NAME,
    MAX_BATCH_SIZE,
)
from helpers.data_processors import xero_info_to_message
from helpers.mappers import xero_iris_mapper
from setup.assistant_initialiser import client_initialisation, retrieve_assistant
from helpers.runners import make_thread, run_thread
from helpers.utility import save_systematic_output, save_uploaded_file
from main import run_all
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

    emit_event("start", message="Analysis initialising...")

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
                
            emit_event("progress", message=f"Mapped {len(messages)} focus targets. Initiating synthesis...")
            
            run_all(
                os.environ.get("AZURE_OPENAI_API_KEY"),
                os.environ.get("AZURE_OPENAI_ENDPOINT"),
                FILE_PATH_OUT,
                API_VERSION,
                ASSISTANT_ID,
                DEPLOYED_MODEL_NAME,
                MAX_BATCH_SIZE,
                messages,
                mp_df,
                client_initialisation,
                retrieve_assistant,
                make_thread,
                run_thread,
                save_systematic_output,
                emit_event
            )
            
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
    """Route to handle initiating the processing task using Xero integration."""
    form = UploadForm()
    
    connections = []
    has_xero_token = current_user.get_xero_token() is not None
    
    if has_xero_token:
        try:
            from integrations.xero_api import XeroClient
            xero_client = XeroClient(
                client_id=os.environ.get("XERO_CLIENT_ID"),
                client_secret=os.environ.get("XERO_CLIENT_SECRET"),
                refresh_token=current_user.get_xero_token().get("refresh_token"),
                user=current_user
            )
            connections = xero_client.list_connections()
        except Exception as e:
            flash(f"Could not load Xero connections: {str(e)}")
            has_xero_token = False
            
    if request.method == "POST" and form.validate_on_submit():
        tenant_id = request.form.get("tenant_id")
        current_year_end = request.form.get("current_year_end")
        comparison_year_end = request.form.get("comparison_year_end")
        
        if not tenant_id:
            flash("Please select a Xero tenant.")
            return redirect(request.url)
            
        flash(f"API Extraction started for tenant.")

        selected_nominal_codes = request.form.getlist("selected_nominal_codes")

        run_id = str(uuid.uuid4())
        thread = threading.Thread(
            target=run_analysis_thread,
            args=(tenant_id, current_user.id, selected_nominal_codes, run_id, current_year_end, comparison_year_end)
        )
        thread.start()

        return redirect(url_for("report_stream", run_id=run_id))

    return render_template("index.html", form=form, connections=connections, has_xero_token=has_xero_token)


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


@app.route("/api/workbench/initialize/<tenant_id>", methods=["GET"])
@login_required
def init_workbench(tenant_id):
    from integrations.xero_api import XeroClient
    from datetime import date
    import json
    import os
    from openai import AzureOpenAI
    from strings.assistant import API_VERSION, DEPLOYED_MODEL_NAME
    
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
        
        try:
            current_date_str = request.args.get('current_year_end')
            if current_date_str:
                report_date = date.fromisoformat(current_date_str)
            else:
                report_date = date.today()
        except ValueError:
            report_date = date.today()
            
        # Fetch Trial Balance directly
        try:
            tb_json = xero_client.get_trial_balance(tenant_id, report_date=report_date)
        except Exception as e:
            tb_json = {}
            
        def extract_tb_rows(rows, target_dict):
            for r in rows:
                if r.get("RowType") == "Row":
                    cells = r.get("Cells", [])
                    if cells and len(cells) > 0 and cells[0].get("Value") != "Total":
                        target_dict[cells[0].get("Value")] = cells
                elif "Rows" in r:
                    extract_tb_rows(r["Rows"], target_dict)
                    
        tb_dict = {}
        if tb_json.get("Reports"):
            extract_tb_rows(tb_json["Reports"][0].get("Rows", []), tb_dict)
            
        summary_lines = []
        for index, (acc_name, cells) in enumerate(tb_dict.items()):
            if index > 30: # Limit to Top 30 accounts to keep token usage fast for the scanner
                break
            # Try to extract the balance value
            balance = ""
            if len(cells) > 1:
                balance = cells[1].get("Value", "")
            summary_lines.append(f"Account: {acc_name}, Balance: {balance}")
            
        context_str = "\n".join(summary_lines)
        
        client = AzureOpenAI(
            api_key=os.environ.get("AZURE_OPENAI_API_KEY"),
            api_version=API_VERSION,
            azure_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT")
        )
        
        prompt = f"""
You are an expert UK accounting AI assistant. Review this excerpt of Xero Trial Balance data:
{context_str}

Please generate a JSON response exactly matching this schema:
{{
  "flags": [
    {{"category": "Subscriptions", "finding": "...", "logic": "..."}}
  ],
  "coa": [
    {{"code": "4000", "name": "Sales Revenue", "exact_xero_name": "EXACT_STRING_FROM_INPUT", "type": "Income", "balance": "£100", "suggestion": "Analyze", "logic": "..."}}
  ]
}}
Limit to max 2 critical flags (e.g. large payments, anomalies) and exactly 5 Chart of Account items to analyze (mark some as 'Skip' and some as 'Analyze' based on materiality). 
CRITICAL: For every item in the `coa` array, `exact_xero_name` MUST be identical to the exact string provided after 'Account: ' in the input data. Make it realistic to a UK Accountant.
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
        
        result_json_str = response.choices[0].message.content
        result_data = json.loads(result_json_str)
        return jsonify({"status": "Success", "data": result_data})
        
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
    app.run(debug=True)
