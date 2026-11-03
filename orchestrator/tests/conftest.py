"""Doubles de test pour l'orchestrateur : aucun cluster n'est requis.

Un état Kubernetes en mémoire remplace l'API : les ressources créées, les
``patch`` et les ``409`` sont observables, ce qui permet de vérifier
l'idempotence, les garde-fous et la réconciliation.
"""

from __future__ import annotations

import copy
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from kubernetes.client.rest import ApiException

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def conflict() -> ApiException:
    return ApiException(status=409, reason="AlreadyExists")


def not_found() -> ApiException:
    return ApiException(status=404, reason="NotFound")


def _obj(**kwargs):
    return SimpleNamespace(**kwargs)


class FakeCore:
    def __init__(self, store: "FakeStore"):
        self.store = store

    # --- namespaces -------------------------------------------------
    def read_namespace(self, name: str):
        ns = self.store.namespaces.get(name)
        if ns is None:
            raise not_found()
        return ns

    def create_namespace(self, body: dict):
        name = body["metadata"]["name"]
        if name in self.store.namespaces:
            raise conflict()
        self.store.namespaces[name] = _obj(
            metadata=_obj(name=name, labels=dict(body["metadata"].get("labels", {})))
        )
        self.store.creates.append(("namespace", name))
        return self.store.namespaces[name]

    def patch_namespace(self, name: str, body: dict):
        ns = self.store.namespaces[name]
        ns.metadata.labels.update(body["metadata"].get("labels", {}))
        self.store.patches.append(("namespace", name))
        return ns

    def delete_namespace(self, name: str):
        if name not in self.store.namespaces:
            raise not_found()
        self.store.deleted_namespaces.append(name)
        self.store.namespaces.pop(name)

    # --- objets namespacés ------------------------------------------
    def _upsert(self, kind: str, namespace: str, body: dict):
        key = (kind, namespace, body["metadata"]["name"])
        if key in self.store.objects:
            self.store.patches.append(key)
            self.store.objects[key].update(copy.deepcopy(body))
        else:
            self.store.objects[key] = copy.deepcopy(body)
            self.store.creates.append(key)
        return self.store.objects[key]

    def _create(self, kind: str, namespace: str, body: dict):
        key = (kind, namespace, body["metadata"]["name"])
        if key in self.store.objects:
            raise conflict()
        self.store.objects[key] = copy.deepcopy(body)
        self.store.creates.append(key)
        return self.store.objects[key]

    def create_namespaced_limit_range(self, namespace: str, body: dict):
        return self._create("limitrange", namespace, body)

    def patch_namespaced_limit_range(self, name: str, namespace: str, body: dict):
        return self._upsert("limitrange", namespace, body)

    def create_namespaced_resource_quota(self, namespace: str, body: dict):
        return self._create("resourcequota", namespace, body)

    def patch_namespaced_resource_quota(self, name: str, namespace: str, body: dict):
        return self._upsert("resourcequota", namespace, body)

    def create_namespaced_service(self, namespace: str, body: dict):
        return self._create("service", namespace, body)

    def patch_namespaced_service(self, name: str, namespace: str, body: dict):
        return self._upsert("service", namespace, body)

    def delete_namespaced_service(self, name: str, namespace: str):
        key = ("service", namespace, name)
        if key not in self.store.objects:
            raise not_found()
        self.store.objects.pop(key)

    def list_pod_for_all_namespaces(self, label_selector: str = ""):
        return _obj(items=[])

    def list_namespaced_pod(self, namespace: str, label_selector: str = ""):
        return _obj(items=[])


class FakeApps:
    def __init__(self, store: "FakeStore"):
        self.store = store

    def create_namespaced_deployment(self, namespace: str, body: dict):
        key = ("deployment", namespace, body["metadata"]["name"])
        if key in self.store.objects:
            raise conflict()
        self.store.objects[key] = copy.deepcopy(body)
        self.store.creates.append(key)
        return body

    def patch_namespaced_deployment(self, name: str, namespace: str, body: dict):
        key = ("deployment", namespace, name)
        existing = self.store.objects.get(key)
        if existing is None:
            raise not_found()
        metadata = body.get("metadata", {})
        for section in ("labels", "annotations"):
            incoming = metadata.get(section)
            if incoming:
                existing.setdefault("metadata", {}).setdefault(section, {}).update(incoming)
        if "spec" in body:
            existing.setdefault("spec", {}).update(copy.deepcopy(body["spec"]))
        self.store.patches.append(key)
        return existing

    def delete_namespaced_deployment(self, name: str, namespace: str):
        key = ("deployment", namespace, name)
        if key not in self.store.objects:
            raise not_found()
        self.store.objects.pop(key)

    def read_namespaced_deployment(self, name: str, namespace: str):
        key = ("deployment", namespace, name)
        if key not in self.store.objects:
            raise not_found()
        return self.store.as_k8s_deployment(key, self.store.objects[key])

    def list_deployment_for_all_namespaces(self, label_selector: str = ""):
        items = []
        for key, body in list(self.store.objects.items()):
            if key[0] != "deployment":
                continue
            labels = body.get("metadata", {}).get("labels", {})
            if not self.store.matches(labels, label_selector):
                continue
            items.append(self.store.as_k8s_deployment(key, body))
        return _obj(items=items)


class FakeNetworking:
    def __init__(self, store: "FakeStore"):
        self.store = store

    def _upsert(self, kind: str, namespace: str, body: dict):
        key = (kind, namespace, body["metadata"]["name"])
        if key in self.store.objects:
            self.store.patches.append(key)
            self.store.objects[key].update(copy.deepcopy(body))
        else:
            self.store.objects[key] = copy.deepcopy(body)
            self.store.creates.append(key)
        return self.store.objects[key]

    def _create(self, kind: str, namespace: str, body: dict):
        key = (kind, namespace, body["metadata"]["name"])
        if key in self.store.objects:
            raise conflict()
        self.store.objects[key] = copy.deepcopy(body)
        self.store.creates.append(key)
        return self.store.objects[key]

    def create_namespaced_network_policy(self, namespace: str, body: dict):
        return self._create("networkpolicy", namespace, body)

    def patch_namespaced_network_policy(self, name: str, namespace: str, body: dict):
        return self._upsert("networkpolicy", namespace, body)

    def create_namespaced_ingress(self, namespace: str, body: dict):
        return self._create("ingress", namespace, body)

    def patch_namespaced_ingress(self, name: str, namespace: str, body: dict):
        return self._upsert("ingress", namespace, body)

    def delete_namespaced_ingress(self, name: str, namespace: str):
        key = ("ingress", namespace, name)
        if key not in self.store.objects:
            raise not_found()
        self.store.objects.pop(key)


class FakeStore:
    """État en mémoire : namespaces, objets namespacés et journal d'appels."""

    def __init__(self):
        self.namespaces: dict[str, object] = {}
        self.objects: dict[tuple, dict] = {}
        self.creates: list[tuple] = []
        self.patches: list[tuple] = []
        self.deleted_namespaces: list[str] = []
        self.ready_replicas: int | None = None
        self.conditions: list = []
        self.creation_offset: timedelta | None = None

    @staticmethod
    def matches(labels: dict, selector: str) -> bool:
        if not selector:
            return True
        for term in selector.split(","):
            if "=" not in term:
                if term not in labels:  # présence de clé
                    return False
                continue
            key, expected = term.split("=", 1)
            if labels.get(key) != expected:
                return False
        return True

    def as_k8s_deployment(self, key: tuple, body: dict):
        spec = body.get("spec", {})
        replicas = spec.get("replicas", 1)
        ready = replicas if self.ready_replicas is None else self.ready_replicas
        created = datetime.now(timezone.utc)
        if self.creation_offset is not None:
            created = created - self.creation_offset
        metadata = body.get("metadata", {})
        return _obj(
            metadata=_obj(
                name=key[2],
                namespace=key[1],
                labels=dict(metadata.get("labels", {})),
                annotations=dict(metadata.get("annotations", {})),
                creation_timestamp=created,
            ),
            spec=_obj(replicas=replicas),
            status=_obj(ready_replicas=ready, conditions=list(self.conditions)),
        )

    def set_ready(self, ready: int | None):
        self.ready_replicas = ready

    def age(self, delta: timedelta | None):
        self.creation_offset = delta

    def add_condition(self, **kwargs):
        self.conditions.append(_obj(**kwargs))

    def deployments(self) -> dict[tuple, dict]:
        return {key: body for key, body in self.objects.items() if key[0] == "deployment"}


@pytest.fixture
def store():
    return FakeStore()


@pytest.fixture
def cfg():
    from gandal.config import Settings

    return Settings(
        base_domain="sslip.io",
        replicas=2,
        orchestrator_token="test-token",
        internal_token="test-internal",
        backend_url="http://backend.test",
        reconcile_interval=1,
        rollout_timeout=300,
        callback_attempts=1,
    )


@pytest.fixture
def backend(store, cfg):
    from gandal.k8s import KubernetesBackend

    return KubernetesBackend(
        core=FakeCore(store),
        apps=FakeApps(store),
        networking=FakeNetworking(store),
        cfg=cfg,
    )


@pytest.fixture
def payload():
    return {
        "deployment_id": 42,
        "project": "mon-app",
        "owner": "Alice.Dupont",
        "namespace": "proj-mon-app",
        "image": "localhost:5000/paas/mon-app",
        "tag": "a1b2c3d4",
        "digest": "sha256:" + "0" * 64,
        "port": 8080,
        "replicas": 2,
    }
