"""Stage an allowlisted runtime and package with the official Dify CLI."""
import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]
FILES = ('manifest.yaml','main.py','pyproject.toml','uv.lock','requirements.txt','README.md','README.ru.md','PRIVACY.md','LICENSE')
DIRS = ('engine','provider','tools','_assets')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cli', default='dify')
    args=parser.parse_args()
    version=tomllib.loads((ROOT/'pyproject.toml').read_text())['project']['version']
    destination=ROOT/f'dist/docling-remote-{version}.difypkg'
    destination.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='docling-remote-package-') as folder:
        stage=Path(folder)/'plugin';stage.mkdir()
        for name in FILES:shutil.copy2(ROOT/name,stage/name)
        for name in DIRS:
            shutil.copytree(ROOT/name,stage/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc','.DS_Store'))
        subprocess.run([args.cli,'plugin','package',str(stage),'-o',str(destination)],check=True)
    with zipfile.ZipFile(destination) as package:
        for name in package.namelist():
            if any(part in name.split('/') for part in ('.env','.git','.venv','.cache','__pycache__','tests','scripts','docs')):
                raise RuntimeError(f'Unexpected package member: {name}')
    digest=hashlib.sha256(destination.read_bytes()).hexdigest()
    (destination.parent/'SHA256SUMS').write_text(f'{digest}  {destination.name}\n')
    print(f'Built {destination.name}: {destination.stat().st_size} bytes, SHA256 {digest}')


if __name__=='__main__':main()
