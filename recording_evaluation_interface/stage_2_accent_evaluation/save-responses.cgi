#!/usr/bin/python3
import json
import os
import re
import sys
import tempfile
from email import policy
from email.parser import BytesParser
from pathlib import Path


DATA_ROOT = Path(
    "<DIRECTORY_TO_SAVE_SURVEY_RESPONSES>"
)
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
ALLOWED_DEVELOPMENT_ORIGINS = {
    "http://localhost:8000",
    "http://127.0.0.1:8000",
}


def respond(status, payload):
    reason = {
        200: "OK",
        204: "No Content",
        400: "Bad Request",
        405: "Method Not Allowed",
        413: "Payload Too Large",
        500: "Internal Server Error",
    }.get(status, "Error")
    print(f"Status: {status} {reason}")
    print("Content-Type: application/json; charset=utf-8")
    print("Cache-Control: no-store")
    origin = os.environ.get("HTTP_ORIGIN", "")
    if origin in ALLOWED_DEVELOPMENT_ORIGINS:
        print(f"Access-Control-Allow-Origin: {origin}")
        print("Vary: Origin")
    print("Access-Control-Allow-Methods: POST, OPTIONS")
    print("Access-Control-Allow-Headers: Content-Type")
    print()
    if status != 204:
        print(json.dumps(payload, separators=(",", ":")))
    raise SystemExit


def clean_identifier(value):
    return re.sub(r"[^a-zA-Z0-9_-]", "_", str(value)).strip("_")


def clean_filename(value):
    filename = Path(str(value or "")).name
    filename = re.sub(r"[^a-zA-Z0-9._-]", "_", filename)
    if filename in {"", ".", ".."}:
        filename = f"evaluation_upload_{os.getpid()}.json"
    return filename


def ensure_directory(directory):
    try:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError as error:
        respond(500, {"ok": False, "error": f"Could not create private data directory: {error}"})


def atomic_write_bytes(path, content):
    temporary_name = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
            temporary_name = temporary.name
            temporary.write(content)
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, path)
    except OSError as error:
        if temporary_name:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass
        respond(500, {"ok": False, "error": f"Could not save response file: {error}"})


def parse_form():
    content_type = os.environ.get("CONTENT_TYPE", "")
    if not content_type.lower().startswith("multipart/form-data"):
        respond(400, {"ok": False, "error": "multipart/form-data is required"})

    try:
        content_length = int(os.environ.get("CONTENT_LENGTH", "0"))
    except ValueError:
        respond(400, {"ok": False, "error": "Invalid Content-Length"})
    if content_length <= 0:
        respond(400, {"ok": False, "error": "Empty request body"})
    if content_length > MAX_RESPONSE_BYTES:
        respond(413, {"ok": False, "error": "Response upload exceeds the 4 MB limit"})

    body = sys.stdin.buffer.read(content_length)
    if len(body) != content_length:
        respond(400, {"ok": False, "error": "Incomplete request body"})

    message = BytesParser(policy=policy.default).parsebytes(
        b"Content-Type: " + content_type.encode("latin-1") + b"\r\n"
        b"MIME-Version: 1.0\r\n\r\n" + body
    )
    if not message.is_multipart():
        respond(400, {"ok": False, "error": "Invalid multipart request"})

    fields = {}
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if not name or part.get_filename() is not None:
            continue
        payload = part.get_payload(decode=True) or b""
        charset = part.get_content_charset() or "utf-8"
        try:
            fields[name] = payload.decode(charset)
        except (LookupError, UnicodeDecodeError):
            respond(400, {"ok": False, "error": f"Invalid text encoding for {name}"})
    return fields


def main():
    method = os.environ.get("REQUEST_METHOD", "")
    if method == "OPTIONS":
        respond(204, {})
    if method != "POST":
        respond(405, {"ok": False, "error": "POST required"})

    fields = parse_form()
    participant_id = clean_identifier(fields.get("participant_id", ""))
    if not participant_id:
        respond(400, {"ok": False, "error": "A valid participant_id is required"})

    responses = fields.get("responses", "")
    response_bytes = responses.encode("utf-8")
    if not response_bytes:
        respond(400, {"ok": False, "error": "Responses are missing"})
    if len(response_bytes) > MAX_RESPONSE_BYTES:
        respond(413, {"ok": False, "error": "Responses exceed the 4 MB limit"})

    try:
        payload = json.loads(responses)
    except json.JSONDecodeError:
        respond(400, {"ok": False, "error": "Responses are not valid JSON"})

    payload_participant = clean_identifier(
        payload.get("participant", {}).get("participant_id", "")
    )
    if payload_participant != participant_id:
        respond(400, {"ok": False, "error": "Payload participant does not match participant_id"})

    filename = clean_filename(fields.get("response_filename", ""))
    if not filename.startswith(f"evaluation_{participant_id}_") or not filename.endswith(".json"):
        respond(400, {"ok": False, "error": "Response filename does not match participant"})

    participant_directory = DATA_ROOT / participant_id
    ensure_directory(participant_directory)
    atomic_write_bytes(participant_directory / filename, response_bytes)
    respond(200, {"ok": True, "saved": filename})


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as error:
        print("Status: 500 Internal Server Error")
        print("Content-Type: application/json; charset=utf-8")
        print("Cache-Control: no-store")
        print()
        print(json.dumps({"ok": False, "error": f"Unhandled CGI error: {error}"}))
