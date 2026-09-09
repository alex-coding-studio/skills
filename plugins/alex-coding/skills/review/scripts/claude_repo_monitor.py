import argparse
import importlib.util
from pathlib import Path
import re

_spec = importlib.util.spec_from_file_location('repo_monitor_core', Path(__file__).with_name('repo_monitor_core.py'))
core = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(core)

BANNER = "started; {interval}s polling; explicit review ownership; stdout delivery; CI wakes only waiting-ci work"


def deliver(message):
    print(message, flush=True)
    return True


def main():
    parser = argparse.ArgumentParser(description="Quiet repository PR events printed for one Claude Code session.")
    core.add_common_arguments(parser)
    parser.add_argument("--session", required=True, help="Stable identifier for the owning Claude Code session")
    args = parser.parse_args()
    core.validate_common(parser, args)
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", args.session):
        parser.error("session must be a stable identifier of letters, digits, dot, underscore or hyphen")
    root = args.state_dir or core.default_root("CLAUDE_CONFIG_DIR", ".claude", args.repository, args.session)
    watch = core.Watch(args.repository, args.session, args.reviewer, root, deliver,
                       ["--session", args.session, "--reviewer", args.reviewer.lower()], args.interval, role="admin")
    watch.bind_identity("session", parser.error)
    if args.ack is not None:
        core.acknowledge(watch.root, args.ack, args.head, args.phase, args.ci)
        return
    core.run(watch, __file__, BANNER.format(interval=args.interval), args.once)


if __name__ == "__main__":
    main()
