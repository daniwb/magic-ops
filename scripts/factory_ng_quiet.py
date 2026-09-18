"""Manual compilation admission and shared CPU affinity for Factory NG."""
import argparse
import json
import os
from pathlib import Path

POLICY = Path(__file__).resolve().parents[1] / 'config/factory-ng-policy.json'


def compilation_status(settings):
    enabled = settings.get('compilation', {}).get('enabled', True)
    allowed = enabled is True
    return {'allowed': allowed, 'enabled': allowed, 'mode': 'manual',
            'message': ('Compilation and testing are enabled.' if allowed else
                        'Compilation and testing are off. Workers keep preparing patches; '
                        'saved patches wait for the dashboard switch. Checks already running finish safely.')}


def apply_resources(settings):
    config = settings.get('resources', {})
    cpus = config.get('cpu_affinity', [])
    if cpus:
        # Use the same absolute set even when an older parent had a narrower
        # affinity. The kernel intersects it with the container's cpuset.
        os.sched_setaffinity(0, set(cpus))
    nice = int(config.get('nice', 0))
    current = os.getpriority(os.PRIO_PROCESS, 0)
    if nice > current:
        os.setpriority(os.PRIO_PROCESS, 0, nice)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='exit 75 when compilation/testing is off')
    parser.add_argument('--exec', dest='command', nargs=argparse.REMAINDER)
    parser.add_argument('--if-enabled-exec', nargs=argparse.REMAINDER,
                        help='skip this maintenance command while compilation/testing is off')
    args = parser.parse_args()
    settings = json.loads(POLICY.read_text())
    if args.check:
        status = compilation_status(settings)
        print(json.dumps(status))
        raise SystemExit(0 if status['allowed'] else 75)
    command = args.command or args.if_enabled_exec
    if args.if_enabled_exec and not compilation_status(settings)['allowed']:
        return
    if command:
        apply_resources(settings)
        os.execvp(command[0], command)
    print(json.dumps(compilation_status(settings)))


if __name__ == '__main__':
    main()
