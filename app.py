import os
from typing import Dict, Any
from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField
from wtforms.validators import DataRequired, NumberRange
from celery import shared_task
from celery.result import AsyncResult
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
from setup.app_factory import create_app, create_celery_app
import dotenv

dotenv.load_dotenv()

# set cwd to the current directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

app = create_app()
celery_app = create_celery_app(app)


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


@shared_task(ignore_result=False)
def async_run_all(
    iris_nl_path: str, acc_xro_tb_path: str, xro_acc_trans_path: str, email: str
) -> Dict[str, Any]:
    """Asynchronous task to run the main process using the provided file paths."""
    try:
        with open(iris_nl_path, "rb") as iris_nl, open(
            acc_xro_tb_path, "rb"
        ) as acc_xro_tb, open(xro_acc_trans_path, "rb") as xro_acc_trans:
            result = run_all(
                os.environ.get("AZURE_OPENAI_API_KEY"),
                os.environ.get("AZURE_OPENAI_ENDPOINT"),
                iris_nl,
                acc_xro_tb,
                xro_acc_trans,
                FILE_PATH_OUT,
                API_VERSION,
                ASSISTANT_ID,
                DEPLOYED_MODEL_NAME,
                MAX_BATCH_SIZE,
                xero_info_to_message,
                xero_iris_mapper,
                client_initialisation,
                retrieve_assistant,
                make_thread,
                run_thread,
                save_systematic_output,
                email,
            )
        return {"status": "Task completed", "result": result}
    except Exception as e:
        return {"status": "Error", "message": str(e)}
    finally:
        os.remove(iris_nl_path)
        os.remove(acc_xro_tb_path)
        os.remove(xro_acc_trans_path)


@shared_task(ignore_result=False)
def async_run_experiment(run_def_payload: dict) -> Dict[str, Any]:
    """Background task to run multi-model experiments."""
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
def upload():
    """Route to handle file uploads and initiate the processing task."""
    form = UploadForm()
    if request.method == "POST" and form.validate_on_submit():
        required_files = ["xro_acc_trans", "acc_xro_tb", "iris_nl"]
        if not all(file in request.files for file in required_files):
            flash("All files are required")
            return redirect(request.url)

        files = {file: request.files[file] for file in required_files}
        if any(file.filename == "" for file in files.values()):
            flash("All files must be selected")
            return redirect(request.url)

        email = request.form.get("email")
        file_paths = {
            name: save_uploaded_file(file, app.config["UPLOAD_FOLDER"])
            for name, file in files.items()
        }

        flash(f"Files uploaded successfully. Confirmation sent to {email}")

        task = async_run_all.delay(
            file_paths["iris_nl"], file_paths["acc_xro_tb"], file_paths["xro_acc_trans"], email
        )

        # Send to result page
        return redirect(url_for("task_status", task_id=task.id))

    return render_template("index.html", form=form)


@app.route("/result/<task_id>")
def task_status(task_id: str):
    """Route to get the status of a background task."""
    task = AsyncResult(task_id)
    if task.state == "PENDING":
        state = task.state
        status = "Task is pending..."
        result = None
        error = None
    elif task.state != "FAILURE":
        state = task.state
        status = task.info.get("status", "")
        result = task.info.get("result") if "result" in task.info else None
        error = None
    else:
        state = task.state
        status = "Error occurred"
        result = None
        error = str(task.info)

    return render_template(
        "result.html", state=state, status=status, result=result, error=error
    )


@app.route("/revoke/<task_id>")
def revoke_task(task_id: str):
    """Route to revoke a background task."""
    task = AsyncResult(task_id)
    task.revoke(terminate=True)
    return jsonify({"task_id": task_id, "status": "Task revoked"})


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


if __name__ == "__main__":
    app.run(debug=True)
