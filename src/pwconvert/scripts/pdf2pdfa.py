#!/usr/bin/env python3

import sys

import typer
from pwconvert.util import run_shell_cmd


app = typer.Typer(rich_markup_mode="rich")


@app.command()
def pdf2pdfa(input_file: str, output_file: str):
    """
    Convert pdf to pdf/a
    """

    cmd = ['gs', '-q', '-dPDFA=2', '-dBATCH', '-dNOPAUSE',
           '-sColorConversionStrategy=RGB', '-sDEVICE=pdfwrite',
           '-dPDFACompatibilityPolicy=1', '-sOutputFile=' + output_file,
           input_file]

    try:
        returncode, out, err = run_shell_cmd(cmd)
    except Exception as e:
        print(e)
        print('out', out)
        print('err', err)
        sys.exit(1)

    return returncode


if __name__ == '__main__':
    typer.run(pdf2pdfa)
