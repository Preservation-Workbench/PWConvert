import os
import signal
import subprocess


def run_shell_command(command, cwd=None, timeout=30, shell=False):
    """Run shell command"""
    os.environ['PYTHONUNBUFFERED'] = "1"
    stdout = []
    stderr = []
    mix = []  # TODO: Fjern denne mm

    # sys.stdout.flush()

    proc = subprocess.Popen(
        command,
        cwd=cwd,
        shell=shell,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )

    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.kill(proc.pid, signal.SIGINT)

    for line in proc.stdout:
        stdout.append(line.rstrip())

    for line in proc.stderr:
        stderr.append(line.rstrip())

    return proc.returncode, stdout, stderr, mix
