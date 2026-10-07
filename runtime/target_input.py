"""Prepare one protein target from local coordinates; no engines or downloads."""
from pathlib import Path
import hashlib, io, json, os


def prepare_target(source, chain, residue_range, expected_sequence, directory,
                   model=1, altloc='occupancy'):
    import numpy as np
    from biotite.sequence import ProteinSequence
    from biotite.structure import get_residue_starts
    from biotite.structure.io.pdb import PDBFile
    from biotite.structure.io.pdbx import CIFFile, get_structure, set_structure

    path = Path(source).expanduser().absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Target input symlinks are refused')
    if not path.is_file() or path.stat().st_size > 64 * 1024**2:
        raise ValueError('Target input missing or exceeds 64 MiB')
    if not isinstance(chain, str) or not chain:
        raise ValueError('Provide the source author chain ID')
    if not isinstance(model, int) or isinstance(model, bool) or model < 1:
        raise ValueError('Model index must be a positive integer')
    if altloc not in ('first', 'occupancy'):
        raise ValueError('Altloc policy must be first or occupancy')
    if residue_range is not None:
        if (not isinstance(residue_range, (tuple, list)) or len(residue_range) != 2
                or any(not isinstance(v, int) or isinstance(v, bool) for v in residue_range)
                or residue_range[0] > residue_range[1]):
            raise ValueError('Residue range must be two inclusive author residue numbers')
    if not isinstance(expected_sequence, str):
        raise ValueError('Expected sequence must be text; empty derives it from coordinates')
    raw = path.read_bytes()
    suffix = path.suffix.lower()
    stream = io.StringIO(raw.decode('utf8'))
    if suffix == '.pdb':
        aa = PDBFile.read(stream).get_structure(model=model, altloc=altloc)
    elif suffix in ('.cif', '.mmcif'):
        aa = get_structure(CIFFile.read(stream), model=model, altloc=altloc,
                           use_author_fields=True)
    else:
        raise ValueError('Supported target formats: .pdb, .cif, .mmcif')
    aa = aa[aa.chain_id == chain]
    if not len(aa):
        raise ValueError('Source author chain does not exist')
    if residue_range is not None:
        aa = aa[(aa.res_id >= residue_range[0]) & (aa.res_id <= residue_range[1])]
    # Water/ligand records are excluded; do not silently drop modified peptide residues.
    for a, b in zip(get_residue_starts(aa, add_exclusive_stop=True)[:-1],
                    get_residue_starts(aa, add_exclusive_stop=True)[1:]):
        if aa.hetero[a] and {'N', 'CA', 'C'}.issubset(set(aa.atom_name[a:b])):
            raise ValueError('Modified/hetero protein residues require a prepared standard target')
    aa = aa[~aa.hetero]
    if not len(aa):
        raise ValueError('Target residue selection is empty')
    starts = get_residue_starts(aa, add_exclusive_stop=True)
    identities = [(int(aa.res_id[a]), str(aa.ins_code[a])) for a in starts[:-1]]
    if len(set(identities)) != len(identities):
        raise ValueError('Duplicate source residue identity')
    numbers = [i for i, _ in identities]
    if residue_range is not None and (residue_range[0] not in numbers or residue_range[1] not in numbers):
        raise ValueError('Selected residue range endpoint does not exist')
    if any(b - a not in (0, 1) for a, b in zip(numbers, numbers[1:])):
        raise ValueError('Source residue numbering has gaps or is out of order; select a continuous segment')
    sequence = []
    mapping = []
    for i, (a, b) in enumerate(zip(starts[:-1], starts[1:]), 1):
        names = list(map(str, aa.atom_name[a:b]))
        if len(set(names)) != len(names) or any(names.count(n) != 1 for n in ('N', 'CA', 'C', 'O')):
            raise ValueError('Missing or duplicate backbone/atom identity in target residue '+str(i))
        try:
            letter = ProteinSequence.convert_letter_3to1(str(aa.res_name[a]))
        except KeyError as exc:
            raise ValueError('Nonstandard target residue '+str(aa.res_name[a])) from exc
        if letter not in 'ACDEFGHIKLMNPQRSTVWY':
            raise ValueError('Target must contain standard protein residues')
        sequence.append(letter)
        mapping.append({'source_chain':chain, 'source_res_id':identities[i-1][0],
                        'source_ins_code':identities[i-1][1], 'target_chain':'A', 'target_res_id':i})
    sequence = ''.join(sequence)
    if expected_sequence and sequence != expected_sequence:
        raise ValueError('Expected target sequence differs from selected coordinates')
    if not np.isfinite(aa.coord).all():
        raise ValueError('Nonfinite target coordinates')
    backbone = aa.coord[np.isin(aa.atom_name, ('N', 'CA', 'C', 'O'))]
    if np.linalg.matrix_rank(backbone - backbone.mean(axis=0)) < 2:
        raise ValueError('Target backbone geometry cannot define an alignment frame')
    aa = aa.copy(); aa.chain_id[:] = 'A'; aa.ins_code[:] = ''
    for i, (a, b) in enumerate(zip(starts[:-1], starts[1:]), 1):
        aa.res_id[a:b] = i
    cif = CIFFile(); set_structure(cif, aa); text = io.StringIO(); cif.write(text)
    normalized = text.getvalue().encode('utf8')
    sha = lambda data: hashlib.sha256(data).hexdigest()
    provenance = {'schema':'design-template-target-v2', 'source_path':str(path.resolve()),
        'source_sha256':sha(raw), 'model_cif_sha256':sha(raw), 'source_chain':chain,
        'source_residue_range':list(residue_range) if residue_range is not None else None,
        'model':model, 'altloc':altloc, 'expected_sequence':expected_sequence,
        'chain':'A', 'sequence':sequence, 'sequence_sha256':sha(sequence.encode()),
        'target_range':[1,len(sequence)], 'target_cif_sha256':sha(normalized),
        'residue_mapping':mapping, 'mapping_sha256':sha(json.dumps(mapping,sort_keys=True).encode()),
        'coordinate_source':'selected local coordinates; author IDs mapped to A1..N; no missing residues invented'}
    directory = Path(directory)
    if any(p.is_symlink() for p in (directory, *directory.parents)):
        raise ValueError('Target preparation directory symlinks are refused')
    directory.mkdir(parents=True, exist_ok=True)
    target = directory/'target.cif'; record = directory/'target.provenance.json'
    if target.is_symlink() or record.is_symlink():
        raise ValueError('Prepared target symlinks are refused')
    if target.exists() or record.exists():
        if (not target.is_file() or not record.is_file()
                or json.loads(record.read_text()) != provenance or target.read_bytes() != normalized):
            raise ValueError('Target input/selection or prepared artifact changed; use a new run')
    else:
        temporary = record.with_suffix('.tmp')
        if temporary.exists() or temporary.is_symlink():
            raise ValueError('Unexpected target provenance temporary file')
        target.write_bytes(normalized)
        temporary.write_text(json.dumps(provenance,ensure_ascii=False,indent=2)+'\n')
        os.replace(temporary,record)
    return aa, sequence, provenance


def verify_prepared_target(source, directory, provenance):
    """Refuse changed input evidence before any scientific stage reads it."""
    source = Path(source).expanduser().absolute()
    directory = Path(directory).absolute()
    target = directory/'target.cif'
    record = directory/'target.provenance.json'
    for path in (source, target, record):
        if any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file():
            raise ValueError('Frozen target input missing or symlinked; use a new run')
    # ponytail: hash full input each stage; optimize only if measured input I/O warrants it.
    if (hashlib.sha256(source.read_bytes()).hexdigest() != provenance['source_sha256']
            or hashlib.sha256(target.read_bytes()).hexdigest() != provenance['target_cif_sha256']
            or json.loads(record.read_text()) != provenance):
        raise ValueError('Frozen target input or prepared artifact changed; use a new run')
