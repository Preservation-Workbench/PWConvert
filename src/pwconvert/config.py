import os
from pathlib import Path
from ruamel.yaml import YAML

pwconv_path = Path(__file__).parent.resolve()
yaml = YAML()

with open(Path(pwconv_path, "../../converters.yml"), "r") as content:
    converters = yaml.load(content)
with open(Path(pwconv_path, "../../application.yml"), "r") as content:
    cfg = yaml.load(content)

_local_converters = {}
if os.path.exists(Path(pwconv_path, '../../converters.local.yml')):
    with open(Path(pwconv_path, '../../converters.local.yml'), 'r') as content:
        _local_converters = yaml.load(content)

_local_cfg = {}
if os.path.exists(Path(pwconv_path, '../../application.local.yml')):
    with open(Path(pwconv_path, "../../application.local.yml"), "r") as content:
        _local_cfg = yaml.load(content)

# Properties set in local files will overwrite those in tracked files
converters.update(_local_converters)
cfg.update(_local_cfg)
