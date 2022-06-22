#!/usr/bin/env python3

import sys
import typer
from pdfy import Pdfy


# TODO: Denne fungerer ikke - problemer med chromedriver og pdfy
def html2pdf(src_file_path: str, target_file_path: str):
    """Convert html to pdf"""
    try:
        p = Pdfy()
        p.html_to_pdf(src_file_path, target_file_path)
    except Exception as e:
        print(e)
        sys.exit(1)


if __name__ == '__main__':
    typer.run(html2pdf)
