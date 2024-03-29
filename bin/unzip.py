import subprocess
from shlex import quote
import typer


def unzip(zipfile, to_dir):
    """ Unzip file with correct encoding for norwegian """
    encoding = None
    for enc in ['IBM850', 'windows-1252']:
        cmd = [f"lsar -e {enc} {quote(zipfile)}"]
        out = run_process(cmd)
        if 'æ' in out or 'ø' in out or 'å' in out:
            encoding = enc
            break

    if encoding:
        cmd = [f"unar -k skip -D -e {encoding} {quote(zipfile)} -o {quote(to_dir)}"]
    else:
        cmd = [f"unar -k skip -D {quote(zipfile)} -o {quote(to_dir)}"]

    run_process(cmd)

    return 0


def run_process(cmd, cwd=None, shell=False):

    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    except Exception as e:
        return e

    return result.stdout


if __name__ == '__main__':
    typer.run(unzip)
