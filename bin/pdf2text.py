#!/usr/bin/env python3

import os
import typer


def pdf2text(file_path: str):
    """
    Convert pdf files to text, by extracting text and leaving objects like images etc. out.

    Args:
        file_path: path for the file to be converted

    Returns:
        bool: True if conversion was successful otherwise False
    """
    split_ext = os.path.splitext(file_path)
    output_file = split_ext[0] + '.txt'

    command = f'gs -sDEVICE=txtwrite -q -dNOPAUSE -dBATCH -sOutputFile="{output_file}" "{file_path}"'
    status_code = os.system(command)

    return True if status_code == 0 else False


if __name__ == '__main__':
    typer.run(pdf2text)
