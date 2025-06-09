from __future__ import annotations
import os
import shutil
import json
import subprocess
from os.path import relpath
from inspect import currentframe, getframeinfo
from pathlib import Path
from typing import Any, Type, Dict
from shlex import quote
import time
import mimetypes

import magic
import chardet

from config import cfg, converters
from util import run_shell_cmd


class File:
    """Contains methods for converting files"""

    def __init__(
        self,
        row: Dict[str, Any],
        pwconv_path: Path,
        unidentify: bool
    ):
        self._pwconv_path = pwconv_path
        self.id = row['id']
        self.path = row['path']
        self.encoding = row['encoding']
        self.status = row['status']
        self.mime = None if unidentify else row['mime']
        self.format = None if unidentify else row['format']
        self.version = None if unidentify else row['version']
        self.size = row['size']
        self.puid = None if unidentify else row['puid']
        self.source_id = row['source_id']
        self._parent = Path(self.path).parent
        self._stem = Path(self.path).stem
        self.ext = Path(self.path).suffix
        self.kept = None if unidentify else row['kept']

    def set_metadata(self, source_path, source_dir):
        if cfg['use_siegfried']:
            cmd = ['sf', '-json', source_path]
            p = subprocess.Popen(cmd, cwd=source_dir, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE)
            out, err = p.communicate()

            self.encoding = None
            if not err:
                fileinfo = json.loads(out)
                self.mime = fileinfo['files'][0]['matches'][0]['mime']
                self.format = fileinfo['files'][0]['matches'][0]['format']
                self.version = fileinfo['files'][0]['matches'][0]['version']
                self.size = fileinfo['files'][0]['filesize']
                self.puid = fileinfo['files'][0]['matches'][0]['id']

        if self.mime in ['', 'None', None]:
            self.mime = magic.from_file(source_path, mime=True)
            self.format = magic.from_file(source_path).split(',')[0]

        if self.mime.startswith('text/'):
            blob = open(source_path, 'rb').read()
            self.encoding = chardet.detect(blob)['encoding']

        extensions = mimetypes.guess_all_extensions(self.mime, strict=False)
        if (
            extensions and self.ext and self.ext.lower() not in extensions and
            self.mime not in [
                'application/octet-stream',
                'application/xml'
                'text/plain'
            ]
        ):
            self._stem = self._stem + self.ext
            self.ext = None

    def get_dest_ext(self, converter, dest_path, orig_ext):
        if 'dest-ext' not in converter:
            dest_ext = self.ext
        else:
            dest_ext = ('' if converter['dest-ext'] is None
                        else '.' + converter['dest-ext'].strip('.'))

        if orig_ext and dest_ext != self.ext:
            dest_ext = self.ext + dest_ext

        return dest_ext

    def get_conversion_cmd(self, converter, source_path, dest_path, temp_path):
        cmd = converter["command"] if 'command' in converter else None

        if cmd:
            if '<temp>' in cmd:
                Path(Path(temp_path).parent).mkdir(parents=True, exist_ok=True)
                cmd = cmd.replace("<temp>", quote(temp_path))

            cmd = cmd.replace("<source>", quote(source_path))
            cmd = cmd.replace("<dest>", quote(dest_path))
            cmd = cmd.replace("<source-parent>",
                              quote(str(Path(source_path).parent)))
            cmd = cmd.replace("<dest-parent>",
                              quote(str(Path(dest_path).parent)))
            cmd = cmd.replace("<pid>", str(os.getpid()))
            cmd = cmd.replace("<stem>", quote(self._stem))

        return cmd

    def is_accepted(self, converter):
        accept = False
        if 'accept' in converter:
            if converter['accept'] is True:
                accept = True
            elif 'version' in converter['accept'] and self.version:
                accept = self.version in converter['accept']['version']
            elif 'encoding' in converter['accept'] and self.encoding:
                accept = self.encoding in converter['accept']['encoding']

        return accept

    def convert(
        self, source_dir: str, dest_dir: str, orig_ext: bool, debug: bool,
        set_source_ext: bool, identify_only: bool, keep_originals: bool
    ) -> dict[str, Type[str]]:
        """
        Convert file to archive format

        Returns
        - path to converted file
        - False if conversion fails
        - None if file isn't converted
        """

        if self.source_id:
            source_path = os.path.join(dest_dir, self.path)
        else:
            source_path = os.path.join(source_dir, self.path)

        if self.mime in ['', 'None', None]:
            self.set_metadata(source_path, source_dir)

        converter = converters[self.mime] if self.mime in converters else {}

        mime_ext = converter.get('ext')
        mime_ext = '.' + mime_ext.lstrip('.') if mime_ext else None
        if not mime_ext:
            if self.mime == 'application/xml':
                # mimetypes.guess_extesion returns '.xsl'
                mime_ext = '.xml'
            else:
                mime_ext = mimetypes.guess_extension(self.mime)

        if set_source_ext and self.source_id is None:
            old_path = str(Path(source_dir, self.path))
            new_path = str(Path(source_dir, self._parent, self._stem + mime_ext))
            shutil.move(old_path, new_path)
            self.ext = mime_ext
            self.path = str(Path(self._parent, self._stem + mime_ext))
            source_path = os.path.join(source_dir, self.path)

        if identify_only:
            return None

        if 'puid' in converter and self.puid in converter['puid']:
            converter.update(converter['puid'][self.puid])
        elif 'source-ext' in converter and self.ext in converter['source-ext']:
            converter.update(converter['source-ext'][self.ext])

        accept = self.is_accepted(converter)

        dest_path = os.path.join(dest_dir, self._parent, self._stem)
        temp_path = os.path.join('/tmp/convert',  self.path)
        dest_path = os.path.abspath(dest_path)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        norm_path = None

        if accept:
            self.status = 'accepted'
            self.kept = True
        elif self.mime == 'application/encrypted':
            self.status = 'protected'
            self.kept = True
        elif 'command' in converter:
            from_path = source_path

            dest_ext = self.get_dest_ext(converter, dest_path, orig_ext)
            dest_path = dest_path + dest_ext

            if from_path.lower() == dest_path.lower():
                os.makedirs(os.path.dirname(temp_path), exist_ok=True)
                shutil.move(source_path, temp_path)
                from_path = temp_path

            cmd = self.get_conversion_cmd(converter, from_path, dest_path,
                                          temp_path)

            # Disabled because not in use, and file command doesn't have version
            # with option --mime-type
            # cmd = cmd.replace("<version>", '"' + self.version + '"')
            timeout = (converter['timeout'] if 'timeout' in converter
                       else cfg['timeout'])

            returncode = 0
            # Don't run convert command if file is converted manually
            if (not os.path.exists(dest_path) or os.path.getsize(dest_path) == self.size):

                returncode, out, err = run_shell_cmd(cmd, cwd=self._pwconv_path,
                                                     shell=True, timeout=timeout)

            if returncode or not os.path.exists(dest_path):
                if os.path.isfile(dest_path):
                    # Remove possibel corrupted file
                    os.remove(dest_path)
                    # Pause to let the file be actually deleted
                    # so that we don't get errors in subsequent code
                    time.sleep(0.1)
                elif os.path.isdir(dest_path):
                    shutil.rmtree(dest_path)
                    time.sleep(0.1)
                if 'file requires a password for access' in out:
                    self.status = 'protected'
                elif out == 'timeout':
                    self.status = 'timeout'
                else:
                    self.status = 'failed'

                if debug:
                    print("\nCommand: " + cmd + f" ({returncode})", end="")
                    if out != 'timeout':
                        print('out', out)
                        print('err', err)

                # Move the file back from temp if it was moved there
                # prior to conversion
                if from_path != source_path:
                    # use shutil.copyfile to not get any file permission error
                    shutil.copyfile(from_path, source_path)
                    os.remove(from_path)

                norm_path = False
                self.kept = True
            else:
                self.status = 'converted'
                norm_path = relpath(dest_path, start=dest_dir)
                if 'keep' in converter and converter['keep'] is True:
                    self.kept = True

            if os.path.isfile(temp_path):
                os.remove(temp_path)
            elif os.path.isdir(temp_path):
                shutil.rmtree(temp_path)

        elif 'keep' in converter and converter['keep'] is False:
            self.status = 'removed'
            self.kept = False
        else:
            self.status = 'skipped'
            self.kept = True

        # Copy file from `source_dir` if it's an original file and
        # it should be kept, accepted or if conversion failed
        copy_path = Path(dest_dir, self.path)
        if self.kept and self.source_id is None:
            mime, encoding = mimetypes.guess_type(self.path)
            if not self.ext or (
                mime is not None and mime != self.mime and
                self.ext != mime_ext and
                self.mime != 'application/octet-stream'
            ):
                self.status = 'renamed'
                self.kept = None
                dest_name = self._stem + ('' if not mime_ext else mime_ext)
                copy_path = Path(dest_dir, self._parent, dest_name)
                norm_path = relpath(copy_path, start=dest_dir)
            if source_dir != dest_dir:
                try:
                    shutil.copyfile(Path(source_dir, self.path), copy_path)
                except Exception as e:
                    frame = getframeinfo(currentframe())
                    filename = frame.filename
                    line = frame.lineno
                    print(filename + ':' + str(line), e)
            elif self.status == 'renamed':
                shutil.move(Path(source_dir, self.path), copy_path)

        if norm_path:
            # Remove file previously moved to dest because it could
            # not be converted
            dest_path = Path(dest_dir, norm_path)
            if (
                not self.kept
                and os.path.isfile(copy_path)
                and str(dest_path).lower() != str(copy_path).lower()
            ):
                copy_path.unlink()

            if os.path.isdir(dest_path):
                return norm_path

            row = {
                'id': None,
                'path': norm_path,
                'encoding': None,
                'status': 'new',
                'size': None,
                'source_id': self.id or self.source_id,
                'kept': False
            }
            new_file = File(row, self._pwconv_path, True)
            new_file.set_metadata(str(dest_path), dest_dir)

            if self.status == 'renamed':
                return new_file

            # If the file is converted again with the same extension,
            # we should accept it. This happens when a pdf can't be
            # converted to pdf/a. Ghostscript writes an ordinary pdf
            if self.id is None and new_file.format == self.format:
                new_file.status = 'failed'
                new_file.kept = True
                norm_file = False
            else:
                norm_file = new_file.convert(source_dir, dest_dir, orig_ext,
                                             debug, set_source_ext, identify_only,
                                             keep_originals)

            return norm_file if norm_file else new_file

        else:
            return False
