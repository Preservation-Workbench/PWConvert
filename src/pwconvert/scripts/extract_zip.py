from shlex import quote
import typer

from pwconvert.util import run_shell_cmd
from pwconvert.config import cfg

app = typer.Typer(rich_markup_mode="markdown")


@app.command()
def extract_zip(zipfile, to_dir):
    """ Unzip file with correct encoding for norwegian """
    encoding = None
    for enc in ['IBM850', 'windows-1252']:
        cmd = [f"lsar -e {enc} {quote(zipfile)}"]
        result, out, err = run_shell_cmd(cmd, shell=True)

        for letter in cfg['special_characters']:
            if letter in out:
                encoding = enc
                break

    if encoding:
        cmd = [f"unar -k skip -D -e {encoding} {quote(zipfile)} -o {quote(to_dir)}"]
    else:
        cmd = [f"unar -k skip -D {quote(zipfile)} -o {quote(to_dir)}"]

    result, out, err = run_shell_cmd(cmd, shell=True)

    if result:
        print(out)
        raise typer.Exit(code=1)

    return None
