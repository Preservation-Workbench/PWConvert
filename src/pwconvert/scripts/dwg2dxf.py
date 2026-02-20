import os
import shutil
from ezdxf.addons import odafc
import typer

app = typer.Typer(rich_markup_mode="markdown")
cwd = os.getcwd()


@app.command()
def dwg2dxf(src_path: str, dest_path: str):

    # Convert to temp folder to avoid problems with chmod
    # if dest_path is on Windows
    tmp_path = '/tmp/file.dxf'
    if os.path.exists(tmp_path):
        os.remove(tmp_path)

    if src_path[0] != '/':
        src_path = os.path.join(cwd, src_path)
    if dest_path[0] != '/':
        dest_path = os.path.join(cwd, dest_path)

    odafc.convert(src_path, tmp_path, version='R2018')
    shutil.copyfile(tmp_path, dest_path)
