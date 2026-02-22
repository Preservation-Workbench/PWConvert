import typer
from .convert import app as convert_app
from .distribute import app as dist_app
from .add_original_ext import app as ext_app
from .copy_source_files import app as copy_app 
from .validate import app as validate_app


app = typer.Typer()

app.add_typer(convert_app)
app.add_typer(dist_app)
app.add_typer(ext_app)
app.add_typer(copy_app)
app.add_typer(validate_app)


@app.callback()
def callback():
    """
    Generic file conversion and other tools used in preservation
    """


# def main() -> None:
#     print("Hello from pwconvert!")
