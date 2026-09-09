import argparse
import json
import re
from pathlib import Path


def validate(packet):
    def fields(value, expected, location):
        if not isinstance(value, dict) or set(value) != expected:
            raise ValueError(f"{location}: expected fields {sorted(expected)}")

    def nonempty(value, location):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{location}: expected nonempty text")

    def identifier(value, location):
        nonempty(value, location)
        if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
            raise ValueError(f"{location}: use letters, digits, hyphens or underscores")

    fields(packet, {"version", "id", "title", "language", "source", "items"}, "packet")
    if type(packet["version"]) is not int or packet["version"] != 1:
        raise ValueError("version: expected 1")
    identifier(packet["id"], "id")
    for key in ("title", "source"):
        nonempty(packet[key], key)
    if packet["language"] not in ("en", "zh"):
        raise ValueError("language: expected en or zh")
    if not isinstance(packet["items"], list) or not packet["items"]:
        raise ValueError("items: expected a nonempty list")
    seen = set()
    for item in packet["items"]:
        if not isinstance(item, dict):
            raise ValueError("item: expected an object")
        kind = item.get("kind")
        if kind not in ("text", "single", "multiple"):
            raise ValueError("kind: expected text, single or multiple")
        expected = {"id", "subject", "question", "context", "kind"}
        fields(item, expected | ({"options"} if kind != "text" else set()), "item")
        identifier(item["id"], "item.id")
        if item["id"] in seen:
            raise ValueError("item.id: duplicate identifier")
        seen.add(item["id"])
        for key in ("subject", "question", "context"):
            nonempty(item[key], key)
        if kind != "text":
            options = item["options"]
            if not isinstance(options, list) or len(options) < 2:
                raise ValueError("options: expected at least two choices")
            for option in options:
                nonempty(option, "option")
            if len({option.strip() for option in options}) != len(options):
                raise ValueError("options: duplicate choice")
    return packet


def generate(packet):
    validate(packet)
    template = (Path(__file__).resolve().parents[1] / "assets" / "response.html").read_text()
    payload = json.dumps(packet, ensure_ascii=True).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return template.replace("__PACKET_JSON__", payload)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("packet", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = generate(json.loads(args.packet.read_text(encoding="utf-8")))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as target:
            target.write(result)
    except (ValueError, OSError) as error:
        parser.exit(1, f"Error: {error}\n")
    print(args.output.resolve())


if __name__ == "__main__":
    main()
