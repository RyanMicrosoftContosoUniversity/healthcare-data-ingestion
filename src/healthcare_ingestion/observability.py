"""Bounded REST evidence collection, supported metrics and reference-aware cleanup."""

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

FABRIC_ENDPOINT = "https://api.fabric.microsoft.com/v1/"


class SameOriginRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        target = urllib.parse.urlsplit(new_url)
        if target.scheme != "https" or target.netloc != "api.fabric.microsoft.com":
            raise ValueError("Do not forward bearer tokens through a cross-origin redirect.")
        return super().redirect_request(request, response, code, message, headers, new_url)


class FabricReadClient:
    def __init__(self, token, transport=None, retries=3, sleeper=time.sleep):
        if not 0 <= retries <= 5:
            raise ValueError("Bounded API retries are required.")
        self.token = token
        self.transport = transport or urllib.request.build_opener(SameOriginRedirect()).open
        self.retries, self.sleep = retries, sleeper

    def get(self, route, max_bytes=8 * 1024 * 1024):
        if not 0 < max_bytes <= 16 * 1024 * 1024:
            raise ValueError("Evidence response budgets must be positive and <=16 MiB.")
        url = urllib.parse.urljoin(FABRIC_ENDPOINT, route)
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or parsed.netloc != "api.fabric.microsoft.com":
            raise ValueError("Do not forward bearer tokens to another origin.")
        for attempt in range(self.retries + 1):
            request = urllib.request.Request(
                url, headers={"Authorization": f"Bearer {self.token()}"}
            )
            try:
                with self.transport(request, timeout=30) as response:
                    body = response.read(max_bytes + 1)
                    if len(body) > max_bytes:
                        raise ValueError("Evidence exceeds the configured response budget.")
                    return body
            except urllib.error.HTTPError as error:
                if error.code not in {429, 500, 502, 503, 504} or attempt == self.retries:
                    raise
                hint = error.headers.get("Retry-After", "")
                if hint.isdigit() and int(hint) > 60:
                    raise
                delay = min(60, int(hint)) if hint.isdigit() else min(30, 2**attempt)
                self.sleep(delay)
        raise RuntimeError("Unreachable retry state.")

    def pages(self, route, max_pages=100):
        initial = urllib.parse.urlsplit(route)
        original_query = dict(urllib.parse.parse_qsl(initial.query))
        seen = set()
        for _ in range(max_pages):
            if route in seen:
                raise ValueError("Repeated continuation link.")
            seen.add(route)
            page = json.loads(self.get(route))
            yield page
            route = page.get("continuationUri")
            if not route:
                token = page.get("continuationToken")
                if not token:
                    return
                query = {**original_query, "continuationToken": token}
                route = urllib.parse.urlunsplit(
                    initial._replace(query=urllib.parse.urlencode(query))
                )
        raise ValueError("Evidence pagination budget exhausted.")


@dataclass(frozen=True)
class SparkAttempt:
    workspace_id: str
    item_id: str
    item_type: str
    livy_id: str
    application_id: str
    attempt_id: str

    def route(self):
        if self.item_type not in {"notebooks", "sparkJobDefinitions", "lakehouses"}:
            raise ValueError("Unsupported session-owning item type.")
        parts = [
            "workspaces",
            self.workspace_id,
            self.item_type,
            self.item_id,
            "livySessions",
            self.livy_id,
            "applications",
            self.application_id,
            self.attempt_id,
        ]
        if any(
            not isinstance(p, str) or not p or "/" in p or "\\" in p or p in {".", ".."}
            for p in parts
        ):
            raise ValueError("Explicit unambiguous Spark attempt identifiers are required.")
        return "/".join(urllib.parse.quote(p, safe="") for p in parts)


def collect_log(
    client,
    attempt,
    kind,
    filename,
    save,
    max_bytes=8 * 1024 * 1024,
    container_id=None,
):
    if kind not in {"driver", "rollingdriver", "executor", "event", "livy"}:
        raise ValueError("Unsupported log kind.")
    if not filename or "/" in filename or "\\" in filename:
        raise ValueError("Log filenames must come from the selected attempt's metadata.")
    base = attempt.route()
    metadata = {
        **attempt.__dict__,
        "kind": kind,
        "filename": filename,
        "collected_at": datetime.now(UTC).isoformat(),
    }
    try:
        expected_length = None
        query = {"type": "driver" if kind == "rollingdriver" else kind}
        if kind == "event":
            route = base + "/logs"
        elif kind == "livy":
            base = base.rsplit("/applications/", 1)[0] + "/applications/none"
            details = json.loads(client.get(base + "/logs?type=livy&meta=true"))
            if details["fileName"] != filename:
                raise ValueError("Livy filename differs from session metadata.")
            expected_length = int(details["length"])
            query["isDownload"] = "true"
            route = base + "/logs?" + urllib.parse.urlencode(query)
        elif kind == "executor":
            if not container_id:
                raise ValueError("An executor container from the selected attempt is required.")
            containers = json.loads(client.get(base + "/logs?type=executor&meta=true"))
            selected = [item for item in containers if item["containerId"] == container_id]
            files = selected[0]["containerLogMeta"] if len(selected) == 1 else []
            files = [item for item in files if item["fileName"] == filename]
            if len(files) != 1:
                raise ValueError("Executor file not uniquely bound to the selected attempt.")
            expected_length = int(files[0].get("length", files[0].get("fileSize")))
            query.update(containerId=container_id, fileName=filename, size=max_bytes)
            # The documented content API omits attemptId; containerId pins its origin.
            route = base.rsplit("/", 1)[0] + "/logs?" + urllib.parse.urlencode(query)
        else:
            query.update(fileName=filename, isDownload="true")
            meta_query = {"type": query["type"], "fileName": filename, "meta": "true"}
            details = json.loads(client.get(base + "/logs?" + urllib.parse.urlencode(meta_query)))
            file_meta = details["containerLogMeta"]
            if file_meta["fileName"] != filename:
                raise ValueError("Driver filename differs from attempt metadata.")
            expected_length = int(file_meta["length"])
            query["containerId"] = details["containerId"]
            route = base + "/logs?" + urllib.parse.urlencode(query)
        if expected_length is not None and expected_length > max_bytes:
            raise ValueError("Log exceeds the complete-file budget; collect smaller rolling files.")
        content = client.get(route, max_bytes=max_bytes)
        if expected_length is not None and len(content) != expected_length:
            raise ValueError("Log changed or response is partial; no complete-file claim.")
        metadata.update(status="COLLECTED", bytes=len(content), artifact=save(content))
    except (urllib.error.HTTPError, OSError, ValueError, KeyError, TypeError) as error:
        metadata.update(status="UNAVAILABLE", reason=type(error).__name__)
    return metadata


def rolling_driver_files(client, attempt, max_pages=20, page_size=1000):
    if not 1 <= max_pages <= 20 or not 1 <= page_size <= 1000:
        raise ValueError("Rolling driver metadata needs bounded page limits.")
    seen = set()
    for page in range(max_pages):
        query = urllib.parse.urlencode(
            {
                "type": "rollingdriver",
                "meta": "true",
                "offset": page * page_size,
                "maxResults": page_size,
            }
        )
        response = json.loads(client.get(attempt.route() + "/logs?" + query))
        files = response["containerLogMeta"]
        for item in files:
            identity = (response["containerId"], item["fileName"])
            if identity in seen:
                raise ValueError("Rolling log pagination repeated a file.")
            seen.add(identity)
            yield {**item, "containerId": response["containerId"]}
        if len(files) < page_size:
            return
    raise ValueError("Rolling log metadata budget exhausted.")


def metric(value=None, source=None, reason=None):
    if value is None:
        return {"value": None, "availability": "UNAVAILABLE", "reason": reason or "Not exposed"}
    return {"value": value, "availability": "AVAILABLE", "source": source}


def emit_logs(client, rule_id, stream, events):
    rows = []
    for event in events:
        reserved = {"TimeGenerated", "Level", "Event", "ExceptionType"}
        rows.append(
            {
                "TimeGenerated": event["TimeGenerated"],
                "Level": event["Level"],
                "Event": event["Event"],
                "ExceptionType": event.get("ExceptionType", ""),
                "Context": {k: v for k, v in event.items() if k not in reserved},
            }
        )
    if rows:
        client.upload(rule_id=rule_id, stream_name=stream, logs=rows)


def cleanup_candidates(artifacts, holds, now=None):
    now = now or datetime.now(UTC)
    eligible = []
    retention = {"generator_export": 5, "staging": 5, "diagnostics": 30, "benchmark": 30}
    for artifact in artifacts:
        if artifact["id"] in holds or artifact.get("protected") or not artifact.get("committed"):
            continue
        if artifact["kind"] not in retention:
            continue
        committed = datetime.fromisoformat(artifact["committed_at"])
        if committed.tzinfo is None:
            raise ValueError("Cleanup evidence requires timezone-aware commitment timestamps.")
        if now - committed >= timedelta(days=retention[artifact["kind"]]):
            eligible.append(artifact)
    return eligible


def cleanup(artifacts, holds, delete, persist, now=None):
    for artifact in cleanup_candidates(artifacts, holds, now):
        record = {"artifact_id": artifact["id"], "status": "RUNNING"}
        persist(record.copy())
        try:
            delete(artifact)
            record["status"] = "SUCCEEDED"
        except Exception as error:
            record.update(status="FAILED", reason=type(error).__name__)
        persist(record.copy())
