"""Tests de contrat : les schémas JSON partagés correspondent au code.

Un décalage entre ``docs/contracts/*.schema.json`` et les modèles Pydantic
casserait l'intégration backend/orchestrateur sans qu'aucun test unitaire ne le
voie. Ces tests comparent les deux sources.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from app.schemas import (
    DeploymentAccepted,
    DeploymentRequest,
    DeploymentState,
)
from gandal.k8s import DeploySpec

CONTRACTS = Path(__file__).resolve().parents[2] / "docs" / "contracts"


def load(name: str) -> dict:
    return json.loads((CONTRACTS / name).read_text(encoding="utf-8"))


def test_contract_files_exist():
    for name in (
        "deployment-request.schema.json",
        "deployment-accepted.schema.json",
        "deployment-status.schema.json",
        "deployment-read.schema.json",
    ):
        assert (CONTRACTS / name).is_file(), name


def test_schemas_are_valid_json_schema():
    for path in CONTRACTS.glob("*.schema.json"):
        Draft202012Validator.check_schema(json.loads(path.read_text(encoding="utf-8")))


def test_request_schema_matches_model(payload):
    schema = load("deployment-request.schema.json")
    validator = Draft202012Validator(schema)

    model = DeploymentRequest(**payload).model_dump()
    errors = list(validator.iter_errors(model))
    assert errors == []


def test_request_schema_rejects_trailing_hyphen(payload):
    schema = load("deployment-request.schema.json")
    validator = Draft202012Validator(schema)

    invalid = dict(payload, project="mon-app-", namespace="proj-mon-app-")
    assert list(validator.iter_errors(invalid))


def test_request_schema_rejects_reserved_namespace_pattern(payload):
    schema = load("deployment-request.schema.json")
    validator = Draft202012Validator(schema)

    invalid = dict(payload, namespace="kube-system")
    assert list(validator.iter_errors(invalid))


def test_accepted_schema_matches_model(payload):
    schema = load("deployment-accepted.schema.json")
    validator = Draft202012Validator(schema)

    model = DeploymentAccepted(
        deployment_ref="orch-42", status="deploying", url="http://mon-app.sslip.io"
    ).model_dump()
    assert list(validator.iter_errors(model)) == []


def test_state_schema_matches_model():
    schema = load("deployment-read.schema.json")
    validator = Draft202012Validator(schema)

    for state in ("deploying", "deployed", "failed"):
        model = DeploymentState(
            deployment_ref="orch-42", status=state, url=None, message=""
        ).model_dump()
        assert list(validator.iter_errors(model)) == []


def test_status_schema_matches_backend_callback():
    schema = load("deployment-status.schema.json")
    validator = Draft202012Validator(schema)

    assert list(validator.iter_errors({"status": "deployed", "url": None, "message": ""})) == []
    assert list(validator.iter_errors({"status": "unknown"})) != []


@pytest.mark.parametrize("status", ["deploying", "deployed", "failed"])
def test_deploy_spec_accepts_contract_payload(payload, status):
    spec = DeploySpec.from_payload(payload)
    assert spec.deployment_id == payload["deployment_id"]
    assert spec.namespace == f"proj-{payload['project']}"
