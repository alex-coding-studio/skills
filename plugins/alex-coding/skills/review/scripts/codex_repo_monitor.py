import argparse
import importlib.util
from pathlib import Path
import re
import shutil

_spec = importlib.util.spec_from_file_location('repo_monitor_core', Path(__file__).with_name('repo_monitor_core.py'))
core = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(core)

_transport_spec = importlib.util.spec_from_file_location(
    "codex_desktop_transport", Path(__file__).resolve().parents[3] / "scripts" / "codex_desktop_transport.py")
desktop_transport = importlib.util.module_from_spec(_transport_spec)
_transport_spec.loader.exec_module(desktop_transport)

BANNER = "started; {interval}s polling; explicit review ownership; delivery only to idle desktop tasks; CI wakes only waiting-ci work"


def deliverer(executable, thread):
    def deliver(message):
        if not desktop_transport.desktop_is_idle(thread):
            return False
        desktop_transport.queue_message(executable, thread, message)
        return True
    return deliver


def main():
    parser = argparse.ArgumentParser(description="Quiet repository PR events delivered to an existing Codex task.")
    core.add_common_arguments(parser)
    parser.add_argument("--thread", required=True, help="Existing verified Codex desktop task UUID")
    parser.add_argument("--codex", default="codex", help="Codex executable with the verified queue capability")
    args = parser.parse_args()
    core.validate_common(parser, args)
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", args.thread):
        parser.error("thread must be an existing task UUID")
    executable = shutil.which(args.codex)
    if not executable:
        parser.error("Codex executable was not found")
    root = args.state_dir or Path.home() / ".codex" / "state" / "repository-monitor" / core.state_key(args.repository, args.thread)
    watch = core.Watch(args.repository, args.thread, args.reviewer, root, deliverer(executable, args.thread),
                       ["--thread", args.thread, "--reviewer", args.reviewer.lower(), "--codex", executable], args.interval, role="admin")
    watch.bind_identity("thread", parser.error)
    if args.ack is not None:
        core.acknowledge(watch.root, args.ack, args.head, args.phase, args.ci)
        return
    core.run(watch, __file__, BANNER.format(interval=args.interval), args.once)


if __name__ == "__main__":
    main()
