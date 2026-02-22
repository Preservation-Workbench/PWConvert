import os
from pathlib import Path
import shutil
import typer
import petl as etl
from .storage import Storage

app = typer.Typer(rich_markup_mode="markdown")
cwd = os.getcwd()


@app.command()
def copy_source_files(source: str, dest: str, db: str, mime: str = None, limit: str = None):
    """ Copy original files to destination folder

    Makes it possible to make copy of files of certain mime type. 
    """

    if source[0] != '/':
        source = os.path.join(cwd, source)
    if dest[0] != '/':
        dest = os.path.join(cwd, dest)
    if db[0] != '/':
        db = os.path.join(cwd, db)
        print('db', db)

    with Storage(db) as store:
        conds, params = store.get_conds(mime=mime, original=True, finished=True)
        files = store.get_rows(conds, params, limit)
        print('files', files)
        count = len(files) - 1
        i = 0
        for file in etl.dicts(files):
            i += 1
            print(f"\r{i} / {count}", end="", flush=True)
            src_path = Path(source, file['path'])
            dst_path = Path(dest, file['path'])
            os.makedirs(os.path.dirname(dst_path), exist_ok=True)
            shutil.copyfile(src_path, dst_path)
        print(f'\ncopied {i} files')


if __name__ == "__main__":
    typer.run(copy_source_files)
