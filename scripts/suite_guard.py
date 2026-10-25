import os
import signal
import subprocess
import sys
import time


def run_suite(budget: float, cmd: list[str]) -> int:
    start = time.monotonic()
    proc = subprocess.Popen(cmd, start_new_session=True)
    try:
        rc = proc.wait(timeout=budget)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGTERM)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
        print(f"suite killed: exceeded {budget:.0f}s budget", file=sys.stderr)
        return 1
    print(f"suite finished in {time.monotonic() - start:.1f}s (budget {budget:.0f}s)")
    return rc


if __name__ == "__main__":
    sys.exit(run_suite(float(sys.argv[1]), sys.argv[2:]))
