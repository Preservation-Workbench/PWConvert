# Copyright(C) 2022 Morten Eek

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import csv
import glob
import os
import pathlib
import re
import shutil
import subprocess
import zipfile
from os.path import relpath
from pathlib import Path
import util

import petl as etl
import typer
from ruamel.yaml import YAML

# Load converters
yaml = YAML()
with open("converters.yml", "r") as yamlfile:
    converters = yaml.load(yamlfile)

pwconv_path = pathlib.Path(__file__).parent.resolve()


class File:
    """Contains methods for converting files"""

    def __init__(self, row):
        self.path = row['source_file_path']
        self.mime_type = row['mime_type']
        self.format = row['format']
        self.version = row['version']
        self.file_size = row['file_size']
        self.id = row['id']
        split_ext = os.path.splitext(self.path)
        # relative path without extension
        self.relative_root = split_ext[0]
        self.ext = split_ext[1][1:]
        self.normalized = {'result': None, 'norm_file_path': None, 'error': None, 'msg': None}

    def convert(self, source_dir: str, target_dir: str):
        """Convert file to archive format"""

        # TODO: Finn ut beste måten å håndtere manuelt konverterte filer
        # if not check_for_files(norm_file_path + '*'):
        if True:
            if self.mime_type == 'n/a':
                self.normalized['msg'] = 'Not a document'
                self.normalized['norm_file_path'] = None
            elif self.mime_type == 'application/zip':
                self._zip_to_norm(source_dir, target_dir)
            else:
                source_file_path = os.path.join(source_dir, self.path)
                target_file_path = os.path.join(target_dir, self.path)

                if self.format not in converters:
                    shutil.copyfile(source_file_path, target_file_path)
                    self.normalized['msg'] = 'Conversion not supported'
                    self.normalized['norm_file_path'] = None
                    return self.normalized

                converter = converters[self.format]

                match self.format:
                    case "Plain Text File":
                        self._convert_txt_file(converter, source_file_path, target_file_path, target_dir)
                    case "Markdown":
                        self._convert_markdown_file(converter, source_file_path, target_file_path, target_dir)
                    case "Hypertext Markup Language":
                        self._convert_html_file(converter, source_file_path, target_file_path, target_dir)
                    case "Extensible Markup Language":
                        """
                        Her kjører vi php skriptet 'convert_sdo.php' håper vi kan endre det til noe annet
                        """
                        self._run_convertion_command(converter, source_file_path, target_file_path, target_dir)
                    case "Acrobat PDF 1.7 - Portable Document Format":
                        self._convert_pdf_file(converter, source_file_path, target_file_path, target_dir)
                    case "Acrobat PDF/A - Portable Document Format":
                        self._convert_pdfa_file(converter, source_file_path, target_file_path, target_dir)

        else:
            self.normalized['msg'] = 'Manually converted'

        return self.normalized

    def _run_convertion_command(self, converter, source_file_path, target_file_path, target_dir):
        """
          Convert function

          Args:
              converter: which converter to use
              source_file_path: source file path for the file to be converted
              target_file_path: target file path for where the conterted file should be saved
              target_dir: path directory where the converted result should be saved
          """
        target_ext = ""
        if 'source-ext' in converter and self.ext in converter['source-ext']:
            cmd = converter['source-ext'][self.ext]['command']

            if 'target-ext' in converter['source-ext'][self.ext]:
                target_ext = converter['source-ext'][self.ext]['target-ext']
        else:
            cmd = converter['command']
        if target_ext and self.ext != target_ext:
            target_file_path = os.path.join(target_dir, self.path + '.' + target_ext)

        cmd = cmd.replace('<source>', '"' + source_file_path + '"')
        cmd = cmd.replace('<target>', '"' + target_file_path + '"')

        print(cmd)
        bin_path = os.path.join(pwconv_path, 'bin')

        result = util.run_shell_command(cmd, cwd=bin_path, shell=True)

        if not os.path.exists(target_file_path):
            self.normalized['msg'] = 'Conversion failed'
            self.normalized['norm_file_path'] = None
        else:
            self.normalized['msg'] = 'Converted successfully'
            self.normalized['norm_file_path'] = target_file_path

        return result

    def _zip_to_norm(self, source_dir, target_dir):
        """Exctract all files, convert them, and zip them again"""

        # TODO: Blir sjekk på om normalisert fil finnes nå riktig
        #       for konvertering av zip-fil når ext kan variere?
        # --> Blir skrevet til tsv som 'converted successfully'
        # --> sjekk hvordan det kan stemme når extension på normalsert varierer

        def copy(norm_dir_path_param, norm_base_path_param):
            files = os.listdir(norm_dir_path_param)
            file = files[0]
            ext = Path(file).suffix
            src = os.path.join(norm_dir_path_param, file)
            dest = os.path.join(
                Path(norm_base_path_param).parent,
                os.path.basename(norm_base_path_param) + '.zip' + ext
            )
            if os.path.isfile(src):
                shutil.copy(src, dest)

        def zip_dir(norm_dir_path_param, norm_base_path_param):
            shutil.make_archive(norm_base_path_param, 'zip', norm_dir_path_param)

        def rm_tmp(rm_paths):
            for path in rm_paths:
                delete_file_or_dir(path)

        norm_base_path = os.path.join(target_dir, self.relative_root)
        norm_zip_path = norm_base_path + '_zip'
        norm_dir_path = norm_zip_path + '_norm'
        paths = [norm_dir_path + '.tsv', norm_dir_path, norm_zip_path]

        extract_nested_zip(self.path, norm_zip_path)

        msg, file_count, errors = convert_folder(norm_zip_path, norm_dir_path, zipped=True)

        if 'succcessfully' in msg:
            func = copy

            if file_count > 1:
                func = zip_dir

            try:
                func(norm_dir_path, norm_base_path)
            except Exception as e:
                print(e)
                return False

            rm_tmp(paths)

            return True

        rm_tmp(paths)
        return False

    def _convert_txt_file(self, converter, source_file_path, target_file_path, target_dir):

        result = self._run_convertion_command(converter, source_file_path, target_file_path, target_dir)

        if not os.path.exists(target_file_path):
            self.normalized['msg'] = 'Conversion failed'
            self.normalized['norm_file_path'] = None
        else:
            self.normalized['msg'] = 'Converted successfully'
            self.normalized['norm_file_path'] = target_file_path

    def _convert_html_file(self, converter, source_file_path, target_file_path, target_dir):

        result = self._run_convertion_command(converter, source_file_path, target_file_path, target_dir)

        if not os.path.exists(target_file_path):
            self.normalized['msg'] = 'Conversion failed'
            self.normalized['norm_file_path'] = None
        else:
            self.normalized['msg'] = 'Converted successfully'
            self.normalized['norm_file_path'] = target_file_path
        return self.normalized

    def _convert_pdf_file(self, converter, source_file_path, target_file_path, target_dir):

        result = self._run_convertion_command(converter, source_file_path, target_file_path, target_dir)

        if not os.path.exists(target_file_path):
            self.normalized['msg'] = 'Conversion failed'
            self.normalized['norm_file_path'] = None
        else:
            self.normalized['msg'] = 'Converted successfully'
            self.normalized['norm_file_path'] = target_file_path
        return result

    def _convert_pdfa_file(self, converter, source_file_path, target_file_path, target_dir):

        result = self._run_convertion_command(converter, source_file_path, target_file_path, target_dir)

        if not os.path.exists(target_file_path):
            self.normalized['msg'] = 'Conversion failed'
            self.normalized['norm_file_path'] = None
        else:
            self.normalized['msg'] = 'Converted successfully'
            self.normalized['norm_file_path'] = target_file_path
        return result

    def _convert_markdown_file(self, converter, source_file_path, target_file_path, target_dir):

        result = self._run_convertion_command(converter, source_file_path, target_file_path, target_dir)

        if not os.path.exists(target_file_path):
            self.normalized['msg'] = 'Conversion failed'
            self.normalized['norm_file_path'] = None
        else:
            self.normalized['msg'] = 'Converted successfully'
            self.normalized['norm_file_path'] = target_file_path
        return result


def run_siegfried(source_dir, target_dir, tsv_path, zipped=False):
    """
    Generate tsv file with info about file types by running

    Args:
        source_dir: the directory containing the files to be checked
        target_dir: The target directory where the csv file will be saved
        tsv_path: The target path for tsv file
        zipped: nothing...
    """
    if not zipped:
        print('\nIdentifying file types...')

    csv_path = os.path.join(target_dir, 'siegfried.csv')
    os.chdir(source_dir)
    subprocess.run(
        'sf -z -csv * > ' + csv_path,
        stderr=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        shell=True

    )

    with open(csv_path, 'r') as csvin, open(tsv_path, 'w') as tsvout:
        csvin = csv.reader(csvin)
        tsvout = csv.writer(tsvout, delimiter='\t')
        for row in csvin:
            tsvout.writerow(row)

    if os.path.exists(csv_path):
        os.remove(csv_path)


def delete_file_or_dir(path):
    """Delete file or directory tree"""
    if os.path.isfile(path):
        os.remove(path)

    if os.path.isdir(path):
        shutil.rmtree(path)


def check_for_files(filepath):
    """Check if files exists"""
    for filepath_object in glob.glob(filepath):
        if os.path.isfile(filepath_object):
            return True

    return False


def extract_nested_zip(zipped_file, to_folder):
    """Extract nested zipped files to specified folder"""
    with zipfile.ZipFile(zipped_file, 'r') as zfile:
        zfile.extractall(path=to_folder)

    for root, dirs, files in os.walk(to_folder):
        for filename in files:
            if re.search(r'\.zip$', filename):
                filespec = os.path.join(root, filename)
                extract_nested_zip(filespec, root)


def remove_fields(table, *args):
    """Remove fields from petl table"""
    for field in args:
        if field in etl.fieldnames(table):
            table = etl.cutout(table, field)
    return table


def add_fields(table, *args):
    """Add fields to petl table"""
    for field in args:
        if field not in etl.fieldnames(table):
            table = etl.addfield(table, field, None)
    return table


def append_tsv_row(tsv_file, row):
    writer = csv.writer(
        tsv_file,
        delimiter='\t',
        quoting=csv.QUOTE_NONE,
        quotechar='',
        lineterminator='\n',
        escapechar='')
    writer.writerow(row)


def convert_folder(source_dir: str, target_dir: str, zipped: bool = False):
    """Convert all files in folder"""
    tsv_source_path = target_dir + '.tsv'
    converted_now = False
    errors = False

    result_file = open(target_dir + '_processed.tsv', 'w')
    tsv_file = open(target_dir + '_processed.tsv', 'w')

    Path(target_dir).mkdir(parents=True, exist_ok=True)

    if not os.path.isfile(tsv_source_path):
        print("im here")
        run_siegfried(source_dir, target_dir, tsv_source_path, zipped)

    table = etl.fromtsv(tsv_source_path)
    table = etl.rename(table,
                       {
                           'filename': 'source_file_path',
                           'tika_batch_fs_relative_path': 'source_file_path',
                           'filesize': 'file_size',
                           'mime': 'mime_type',
                           'Content_Type': 'mime_type',
                           'Version': 'version'
                       },
                       strict=False)

    table = etl.select(table, lambda rec: rec.source_file_path != '')
    # Remove listing of files in zip
    table = etl.select(table, lambda rec: '#' not in rec.source_file_path)
    # TODO: Ikke fullgod sjekk på embedded dokument i linje over da # faktisk kan forekomme i filnavn
    table.row_count = etl.nrows(table)

    file_count = sum([len(files) for r, d, files in os.walk(source_dir)])

    if table.row_count == 0:
        print('No files to convert. Exiting.')
        return 'Error', file_count
    if file_count != table.row_count:
        print('Row count: ' + str(table.row_count))
        print('File count: ' + str(file_count))
        print("Files listed in '" + tsv_source_path + "' doesn't match files on disk. Exiting.")
        return 'Error', file_count
    if not zipped:
        print('Converting files..')

    table = add_fields(table, 'version', 'norm_file_path', 'result', 'id')

    # Remove Siegfried generated columns
    table = remove_fields(table, 'namespace', 'basis', 'warning')

    append_tsv_row(tsv_file, etl.header(table))

    # Treat csv (detected from extension only) as plain text:
    table = etl.convert(table, 'mime_type',
                        lambda v, _row: 'text/plain' if _row.id == 'x-fmt/18' else v,
                        pass_row=True)

    # Update for missing mime types where id is known:
    table = etl.convert(table, 'mime_type',
                        lambda v, _row: 'application/xml' if _row.id == 'fmt/979' else v,
                        pass_row=True)

    table.row_count = 0
    for row in etl.dicts(table):
        # Remove Thumbs.db files
        if os.path.basename(row['source_file_path']) == 'Thumbs.db':
            os.remove(row['source_file_path'])
            file_count -= 1
            continue

        table.row_count += 1

        row['mime_type'] = row['mime_type'].split(';')[0]

        if not row['mime_type']:
            # Siegfried sets mime type only to xml files with xml declaration
            if os.path.splitext(row['source_file_path'])[1].lower() == '.xml':
                row['mime_type'] = 'application/xml'

        if not zipped:
            print('(' + str(table.row_count) + '/' + str(file_count) + '): ' +
                  '.../' + row['source_file_path'] + ' (' + row['mime_type'] + ')')

        if row['result'] not in ('Converted successfully', 'Manually converted'):
            source_file = File(row)
            normalized = source_file.convert(source_dir, target_dir)

            row['result'] = normalized['msg']

            if row['result'] in ('Conversion failed', 'Conversion not supported'):
                errors = True
                result_file.write(row['result'] + ': ' + row['source_file_path'] +
                                  ' (' + row['mime_type'] + ')\n')
                print(row['mime_type'] + " " + row['result'])

            if row['result'] in ('Converted successfully', 'Manually converted'):
                converted_now = True

            if normalized['norm_file_path']:
                row['norm_file_path'] = relpath(normalized['norm_file_path'], target_dir)

        append_tsv_row(tsv_file, list(row.values()))

    shutil.move(tsv_file.name, tsv_source_path)
    result_file.close()
    tsv_file.close()

    if converted_now:
        msg = 'All files converted succcessfully.'
        if errors:
            msg = "Not all files were converted. See '" + result_file.name + "' for details."
    else:
        msg = 'All files converted previously.'

    print("\n" + msg)

    return msg, file_count, errors


if __name__ == "__main__":
    typer.run(convert_folder)
