import subprocess
import sys


def run(script: str) -> None:
    print(f"\n=== Running {script} ===")
    subprocess.run([sys.executable, script], check=True)


def main() -> None:
    run("update_data.py")
    run("build_rankings.py")
    run("update_readme.py")


if __name__ == "__main__":
    main()
