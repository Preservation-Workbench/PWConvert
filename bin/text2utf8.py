#!/usr/bin/env python3

import os
import re
import typer
import cchardet as chardet


def text2utf8(input_file: str, output_file: str):
    """
    Convert text files to utf8 with Linux file endings
    target extension : .txt

    Args:
        input_file: path for the file to be converted
        output_file: path for the converted file

    Returns:
        The path to the converted file, otherwise an empty string.
    """

    # TODO: Test å bruke denne heller enn/i tillegg til replace under:
    #       https://ftfy.readthedocs.io/en/latest/

    repls = (
        ('‘', 'æ'),
        ('›', 'ø'),
        ('†', 'å'),
        ('&#248;', 'ø'),
        ('&#229;', 'å'),
        ('&#230;', 'æ'),
        ('&#197;', 'Å'),
        ('&#216;', 'Ø'),
        ('&#198;', 'Æ'),
        ('=C2=A0', ' '),
        ('=C3=A6', 'æ'),
        ('=C3=B8', 'ø'),
        ('=C3=A5', 'å'),
    )

    with open(output_file, 'wb') as file:
        with open(input_file, 'rb') as file_r:
            content = file_r.read()
            if content is None:
                return ''

            windows_line_ending = b'\r\n'
            unix_line_ending = b'\n'
            content = content.replace(windows_line_ending, unix_line_ending)

            char_enc = chardet.detect(content)['encoding']

            try:
                data = content.decode(char_enc)
            except UnicodeDecodeError:
                return ''

            for k, v in repls:
                data = re.sub(k, v, data, flags=re.MULTILINE)

        try:
            file.write(data.encode('utf8'))
        except UnicodeEncodeError:
            return ''

        return output_file if os.path.exists(output_file) else ''


if __name__ == '__main__':
    typer.run(text2utf8)
