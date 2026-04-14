from __future__ import annotations

import json
import logging
import sys

from snowl_mobile.runtime.worker_protocol import WorkerRunRequest, WorkerSpec
from snowl_mobile.runtime.worker_service import DummyWorkerService


LOGGER = logging.getLogger(__name__)


def _write_message(payload: dict[str, object]) -> None:
    sys.stdout.write(json.dumps(payload, sort_keys=True) + "\n")
    sys.stdout.flush()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    service = DummyWorkerService()
    current_spec: WorkerSpec | None = None

    for raw_line in sys.stdin:
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        message = json.loads(raw_line)
        message_type = message.get("type")

        if message_type == "initialize":
            current_spec = WorkerSpec.from_mapping(dict(message["worker_spec"]))
            handshake = service.initialize(current_spec)
            _write_message({"type": "initialized", "handshake": handshake.to_dict()})
            continue

        if message_type == "run_trial":
            request = WorkerRunRequest.from_mapping(dict(message["request"]))
            behavior = request.trial.env_vars.get("SNOWL_DUMMY_WORKER_BEHAVIOR")
            if behavior == "malformed":
                sys.stdout.write("this-is-not-json\n")
                sys.stdout.flush()
                continue
            result = service.run_trial(request)
            _write_message({"type": "trial_result", "result": result.to_dict()})
            continue

        if message_type == "shutdown":
            _write_message(
                {
                    "type": "shutdown_ack",
                    "worker_id": None if current_spec is None else current_spec.worker_id,
                }
            )
            return 0

        LOGGER.error("unknown worker message type: %s", message_type)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
