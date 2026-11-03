"""Tests du module Kubernetes : idempotence, garde-fous, état."""

from __future__ import annotations

from datetime import timedelta

import pytest

from gandal.k8s import (
    STATUS_DEPLOYED,
    STATUS_DEPLOYING,
    STATUS_FAILED,
    DeploySpec,
    InvalidDeployment,
    KubernetesBackend,
)
from gandal.names import normalize_label_value

RESOURCES = ("namespace", "limitrange", "resourcequota", "networkpolicy",
             "deployment", "service", "ingress")


def test_apply_creates_all_resources(backend, store, payload):
    spec = DeploySpec.from_payload(payload, backend.cfg)
    url = backend.apply(spec)

    assert url == "http://mon-app.sslip.io"
    created = {key[0] for key in store.creates}
    assert set(RESOURCES) <= created
    assert store.patches == []


def test_apply_is_idempotent(backend, store, payload):
    spec = DeploySpec.from_payload(payload, backend.cfg)
    backend.apply(spec)
    patches_before = len(store.patches)

    backend.apply(spec)

    # 6 objets namespacés (le namespace n'est pas dans ``objects``) : aucun doublon.
    assert len(store.objects) == 6
    assert len(store.patches) > patches_before


def test_image_ref_prefers_digest(backend, payload):
    spec = DeploySpec.from_payload(payload, backend.cfg)
    assert spec.image_ref == f"{payload['image']}@sha256:{'0' * 64}"

    without_digest = dict(payload, digest=None)
    spec = DeploySpec.from_payload(without_digest, backend.cfg)
    assert spec.image_ref == f"{payload['image']}:{payload['tag']}"


def test_labels_normalise_owner(backend, store, payload):
    spec = DeploySpec.from_payload(payload, backend.cfg)
    backend.apply(spec)

    deployment = store.deployments()[("deployment", "proj-mon-app", "mon-app")]
    labels = deployment["metadata"]["labels"]
    assert labels["gandal.io/owner"] == "alice.dupont"
    assert labels["gandal.io/project"] == "mon-app"
    assert labels["gandal.io/app"] == "mon-app"
    assert labels["gandal.io/managed"] == "true"
    assert labels["gandal.io/deployment-id"] == "42"


def test_deployment_annotation_carries_state(backend, store, payload):
    spec = DeploySpec.from_payload(payload, backend.cfg)
    backend.apply(spec)

    annotations = store.deployments()[("deployment", "proj-mon-app", "mon-app")][
        "metadata"
    ]["annotations"]
    assert annotations["gandal.io/deployment-id"] == "42"
    assert annotations["gandal.io/url"] == "http://mon-app.sslip.io"


# ------------------------------------------------------------- garde-fous
@pytest.mark.parametrize(
    "namespace",
    ["kube-system", "default", "kube-public", "kube-node-lease", "gandal-system"],
)
def test_reserved_namespace_refused(payload, namespace):
    with pytest.raises(InvalidDeployment, match="réservé"):
        DeploySpec.from_payload(dict(payload, namespace=namespace))


def test_namespace_must_match_project(payload):
    with pytest.raises(InvalidDeployment, match="incohérent"):
        DeploySpec.from_payload(dict(payload, namespace="proj-autre-app"))


def test_namespace_must_follow_convention(payload):
    with pytest.raises(InvalidDeployment, match="hors convention"):
        DeploySpec.from_payload(dict(payload, namespace="autre-namespace"))


def test_invalid_names_are_refused(payload):
    for bad in ("Mon-App", "mon_app", "-mon-app", "mon-app-", "a" * 64):
        with pytest.raises(InvalidDeployment):
            DeploySpec.from_payload(
                dict(payload, project=bad, namespace=f"proj-{bad}")
            )


def test_invalid_port_and_replicas(payload):
    with pytest.raises(InvalidDeployment, match="port"):
        DeploySpec.from_payload(dict(payload, port=70000))
    with pytest.raises(InvalidDeployment, match="replicas"):
        DeploySpec.from_payload(dict(payload, replicas=0))
    with pytest.raises(InvalidDeployment, match="replicas"):
        DeploySpec.from_payload(dict(payload, replicas=99))


def test_missing_fields(payload):
    for field in ("deployment_id", "project", "namespace", "image", "port"):
        incomplete = dict(payload)
        incomplete.pop(field)
        with pytest.raises(InvalidDeployment, match="manquants"):
            DeploySpec.from_payload(incomplete)


# ------------------------------------------------------------ suppression
def test_delete_requires_managed_label(backend, store, payload):
    spec = DeploySpec.from_payload(payload, backend.cfg)
    backend.apply(spec)

    backend.delete_namespace("proj-mon-app")
    assert store.deleted_namespaces == ["proj-mon-app"]

    backend.apply(spec)
    store.namespaces["proj-mon-app"].metadata.labels.pop("gandal.io/managed", None)
    with pytest.raises(InvalidDeployment, match="non géré"):
        backend.delete_namespace("proj-mon-app")


def test_delete_refuses_reserved_namespace(backend):
    with pytest.raises(InvalidDeployment, match="réservé"):
        backend.delete_namespace("kube-system")


# ------------------------------------------------------------------ état
def test_state_deploying_then_deployed(backend, store, payload):
    spec = DeploySpec.from_payload(payload, backend.cfg)
    backend.apply(spec)
    store.set_ready(0)

    deployment = backend.read_deployment(42)
    assert backend.state_of(deployment).status == STATUS_DEPLOYING

    store.set_ready(2)
    deployment = backend.read_deployment(42)
    assert backend.state_of(deployment).status == STATUS_DEPLOYED


def test_state_failed_after_timeout(backend, store, payload):
    spec = DeploySpec.from_payload(payload, backend.cfg)
    backend.apply(spec)
    store.set_ready(0)
    store.age(timedelta(seconds=backend.cfg.rollout_timeout + 5))

    state = backend.state_of(backend.read_deployment(42))
    assert state.status == STATUS_FAILED
    assert "délai" in state.message


def test_state_failed_on_progress_deadline(backend, store, payload):
    spec = DeploySpec.from_payload(payload, backend.cfg)
    backend.apply(spec)
    store.set_ready(0)
    store.add_condition(
        type="Progressing",
        status="False",
        reason="ProgressDeadlineExceeded",
        message="ReplicaSet a dépassé son délai",
    )

    state = backend.state_of(backend.read_deployment(42))
    assert state.status == STATUS_FAILED
    assert "délai" in state.message


def test_read_unknown_deployment(backend):
    assert backend.read_deployment(999) is None


# ------------------------------------------------------- normalisation
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Alice", "alice"),
        ("alice.dupont", "alice.dupont"),
        ("jean_durand", "jean_durand"),
        ("--bob--", "bob"),
        ("", "unknown"),
        ("A" * 80, "a" * 63),
    ],
)
def test_normalize_label_value(raw, expected):
    assert normalize_label_value(raw) == expected


def test_backend_exposes_namespace_helper():
    from gandal.k8s import namespace_for

    assert namespace_for("mon-app") == "proj-mon-app"


def test_backend_type(backend):
    assert isinstance(backend, KubernetesBackend)
