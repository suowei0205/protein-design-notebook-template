"""Copy the blank template without overwriting any existing project."""
from pathlib import Path
import argparse,shutil
from build import ROOT,build

def create(destination):
 destination=Path(destination).expanduser().absolute()
 if any(p.is_symlink() for p in (destination,*destination.parents)):raise ValueError('Destination symlink refused')
 destination=destination.resolve()
 for protected in ('runtime','template','examples','scripts','tests','.git'):
  if destination.is_relative_to(ROOT/protected):raise ValueError('Choose a separate project directory')
 build(check=True)
 if destination.exists():raise FileExistsError('Project already exists: '+str(destination))
 source=ROOT/'template'
 if any(p.is_symlink() for p in source.rglob('*')):raise ValueError('Template contains a symlink')
 shutil.copytree(source,destination,ignore=shutil.ignore_patterns('run_*','.resources','.run_names.lock','__pycache__','.ipynb_checkpoints'))
 print('CREATED',destination/'DesignProject/DesignProject.ipynb','— no scientific computation')
if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('destination',help='e.g. projects/MyTarget');create(parser.parse_args().destination)
