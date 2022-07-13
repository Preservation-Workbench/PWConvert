#!/usr/bin/env python3

import os
import typer

from util import run_shell_command


def office2pdf(source_file: str, target_file: str):
    """
    Convert office files to pdf

    Args:
        source_file: path for the file to be converted
        target_file: path for the converted file

    Returns:
        Nothing
    """
    target_dir = os.path.dirname(target_file)
    docbuilder_file = os.path.join(target_dir, 'x2x.docbuilder')

    docbuilder = [
        f'builder.OpenFile("{source_file}", "")',
        f'builder.SaveFile("pdf", "{target_file}")',
        'builder.CloseFile();',
    ]

    with open(docbuilder_file, 'w+') as file:
        file.write('\n'.join(docbuilder))

    command = ['documentbuilder', docbuilder_file]
    run_shell_command(command)

    if os.path.isfile(docbuilder_file):
        os.remove(docbuilder_file)


if __name__ == '__main__':
    typer.run(office2pdf)
