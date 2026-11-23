import json
import os
import platform
import subprocess


def main() -> None:
    """Print machine and cluster facts as JSON."""
    with open("/proc/cpuinfo") as f:
        cpu = [
            line.split(":", 1)[1].strip() for line in f if line.startswith("model name")
        ]
    with open("/proc/meminfo") as f:
        mem_kb = int(next(line for line in f if line.startswith("MemTotal")).split()[1])
    kind = subprocess.run(
        ["kind", "version"], check=False, capture_output=True, text=True
    ).stdout.strip()
    print(
        json.dumps(
            {
                "cpu_model": cpu[0] if cpu else "unknown",
                "cpu_threads": os.cpu_count(),
                "ram_gb": round(mem_kb / 1048576, 1),
                "kernel": platform.release(),
                "kind": kind,
                "topology": "single-node kind, load generator on the same machine",
            }
        )
    )


if __name__ == "__main__":
    main()
