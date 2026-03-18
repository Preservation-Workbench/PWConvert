# Scripts

This document describes scripts that can be used for conversion and are installed when installing PWConvert. Some scripts are installed when running `uv tool install`, others when running `install.sh`.

## `abiword`

Convert rtf to pdf:
`abiword --to=pdf --import-extension=rtf <source> -o <dest>`

## `convert`

Converts between different image formats using ImageMagick.
Format of output file is decided by extension.

`convert <source> <dest>`

## `dwg2dfx`

Converts dwg to dxf using ODAFileConverter.

`dwg2dxf <source> <dest>`

## `dwg2pdf`

Converts dwg to pdf. Use option `--dark-bg` for dark background

`dwg2pdf <source> <dest>`

## `dxf2pdf`

Converts dxf to pdf.

`dxf2pdf <source> <dest>`

## `extract_zip`

Unpacks zip files and try to find the correct encoding
for file names. Uses config option `special_characters`
to test encoding 'IBM850' and 'windows-1252'.

## `office2pdf`

Converts office files to pdf with OnlyOffice. Installed with `uv tool install`.

Better compatibilty with MS Office than LibreOffice,
so the resulting pdf often looks better than conversion using
unoconvert. But the conversion is much slower than with unoconvert.

The version distributed wit PWConvert is free, but more recent
versions are not.

`office2pdf <source> <dest>`

## `pandoc`

Converts between many document formats.
File extension on in- and out-file decides output file format.

`pandoc <source> -s -o <dest>`

## `pdf2pdfa`

Converts pdf to pdf/a with Ghostscript. Installed with `uv tool install`
Produces version PDF/A-2.

`pdf2pdfa <source> <dest>`

To validate a pdf before converting to pdf/a, the following config can
be used:

~~~ yaml
application/pdf:
  command: if ! <accept>; then pdfcpu validate <source> && pdf2pdfa <source> <dest>; fi
  dest-ext: pdf
  accept:
    version: [1a, 1b, 2a, 2b]
~~~

## `unoconvert`

Converts with LibreOffice all formats supported by this office suite.
It can convert directly to pdf/a by setting option
`--filter-option SelectPdfVersion=2 `

This is the default converter for office files.

Much faster than office2pdf, which uses OnlyOffice,
but compatibility with MS Office formats is not as good,
so the resulting pdf is sometimes poorly formatted.

`unoconvert --convert-to pdf <source> <dest>`

## `wkhtmltopdf`

Convert html to pdf using QT Webkit rendering engine.

`wkhtmltopdf -O Landscape <source> <dest>`




