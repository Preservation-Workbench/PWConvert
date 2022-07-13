#!/usr/bin/env python3
import os
import sys
import typer

from util import run_shell_command


def unoconv2x(source_path: str, target_path: str, target_ext: str, mime_type: str):
    """
    Convert office files to pdf or html

    Args:
        source_path: path for the file to be converted
        target_path: path for the converted file
        target_ext: extension for the file-format to convert to
        mime_type: the mime-type of the source file
    Returns:
        Nothing if successful otherwise exits with exit code 1
    """
    command = ['unoconv', '-f', target_ext]

    if mime_type in (
            'application/vnd.ms-excel',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    ):
        if target_ext == 'pdf':
            command.extend([
                '-d', 'spreadsheet', '-P', 'PaperOrientation=landscape',
                '-eSelectPdfVersion=1'
            ])
        elif target_ext == 'html':
            command.extend(
                ['-d', 'spreadsheet', '-P', 'PaperOrientation=landscape'])
    elif mime_type in ('application/msword', 'application/rtf'):
        command.extend(['-d', 'document', '-eSelectPdfVersion=1'])

    command.extend(['-o', '"' + target_path + '"', '"' + source_path + '"'])
    run_shell_command(command)

    if not os.path.exists(target_path):
        sys.exit(1)


if __name__ == "__main__":
    typer.run(unoconv2x)
