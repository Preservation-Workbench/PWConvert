import importlib.resources as pkg_resources
from pathlib import Path
from ruamel.yaml import YAML

pwconv_path = Path(__file__).parent.resolve()
yaml = YAML()

default_resource = pkg_resources.files("pwconvert").joinpath("converters.yml")
converters = yaml.load(default_resource.read_text())
default_resource = pkg_resources.files("pwconvert").joinpath("application.yml")
cfg = yaml.load(default_resource.read_text())

user_converter_path = Path.home() / ".config" / "pwconvert" / "converters.yml"
user_cfg_path = Path.home() / ".config" / "pwconvert" / "application.yml"

if user_converter_path.exists():
    with open(user_converter_path, "r") as content:
        user_converters = yaml.load(content)
    if user_converters:
        converters.update(user_converters)

if user_cfg_path.exists():
    with open(user_cfg_path, "r") as content:
        user_cfg = yaml.load(content)
    if user_cfg:
        cfg.update(user_cfg)
