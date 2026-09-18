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
    "<DIRECTORY_TO_SAVE_AUDIO_RECORDINGS_AND_SURVEY RESPONSES>"
)
MAX_RECORDING_BYTES = 10 * 1024 * 1024
MAX_METADATA_BYTES = 2 * 1024 * 1024
ALLOWED_AUDIO_EXTENSIONS = {".webm", ".m4a", ".ogg", ".wav"}
ALLOWED_DEVELOPMENT_ORIGINS = {
    "http://localhost:8000",
    "http://127.0.0.1:8000",
}
MAX_REQUEST_BYTES = MAX_RECORDING_BYTES + (1024 * 1024)


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


def clean_filename(value, fallback_extension):
    filename = Path(str(value or "")).name
    filename = re.sub(r"[^a-zA-Z0-9._-]", "_", filename)
    if filename in {"", ".", ".."}:
        filename = f"upload_{os.getpid()}.{fallback_extension}"
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
        respond(500, {"ok": False, "error": f"Could not save file: {error}"})


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
    if content_length > MAX_REQUEST_BYTES:
        respond(413, {"ok": False, "error": "Upload request is too large"})

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
    files = {}
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        payload = part.get_payload(decode=True) or b""
        filename = part.get_filename()
        if filename is not None:
            files[name] = (filename, payload)
        else:
            charset = part.get_content_charset() or "utf-8"
            try:
                fields[name] = payload.decode(charset)
            except (LookupError, UnicodeDecodeError):
                respond(400, {"ok": False, "error": f"Invalid text encoding for {name}"})
    return fields, files


def save_recording(files, participant_directory, participant_id):
    if "recording" not in files:
        respond(400, {"ok": False, "error": "No recording uploaded"})

    uploaded_filename, content = files["recording"]
    filename = clean_filename(uploaded_filename, "webm")
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_AUDIO_EXTENSIONS:
        respond(400, {"ok": False, "error": "Unsupported recording file extension"})
    if not filename.startswith(participant_id + "_"):
        respond(400, {"ok": False, "error": "Recording filename does not match participant"})

    if not content:
        respond(400, {"ok": False, "error": "Recording is empty"})
    if len(content) > MAX_RECORDING_BYTES:
        respond(413, {"ok": False, "error": "Recording exceeds the 10 MB limit"})

    atomic_write_bytes(participant_directory / filename, content)
    respond(200, {"ok": True, "saved": filename})


def save_metadata(fields, participant_directory, participant_id):
    metadata = fields.get("metadata", "")
    metadata_bytes = metadata.encode("utf-8")
    if not metadata_bytes:
        respond(400, {"ok": False, "error": "Metadata is missing"})
    if len(metadata_bytes) > MAX_METADATA_BYTES:
        respond(413, {"ok": False, "error": "Metadata exceeds the 2 MB limit"})

    try:
        json.loads(metadata)
    except json.JSONDecodeError:
        respond(400, {"ok": False, "error": "Metadata is not valid JSON"})

    filename = clean_filename(fields.get("metadata_filename", ""), "json")
    if not filename.startswith(f"recording_{participant_id}_"):
        respond(400, {"ok": False, "error": "Metadata filename does not match participant"})

    atomic_write_bytes(participant_directory / filename, metadata_bytes)
    respond(200, {"ok": True, "saved": filename})


def main():
    method = os.environ.get("REQUEST_METHOD", "")
    if method == "OPTIONS":
        respond(204, {})
    if method != "POST":
        respond(405, {"ok": False, "error": "POST required"})

    fields, files = parse_form()
    participant_id = clean_identifier(fields.get("participant_id", ""))
    if not participant_id:
        respond(400, {"ok": False, "error": "A valid participant_id is required"})

    participant_directory = DATA_ROOT / participant_id
    ensure_directory(participant_directory)

    action = fields.get("action", "")
    if action == "recording":
        save_recording(files, participant_directory, participant_id)
    if action == "metadata":
        save_metadata(fields, participant_directory, participant_id)
    respond(400, {"ok": False, "error": "Unknown upload action"})


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
