"""Resolve merge conflicts with the tag side and preserve BuildFolder for review."""
from pathlib import PurePosixPath
from .workflow import command


def unmerged(repo):
    result = command(repo, 'ls-files', '-u', '-z')
    files = {}
    for entry in result.stdout.split('\0'):
        if not entry:
            continue
        metadata, path = entry.split('\t', 1)
        _, _, stage = metadata.split(' ')
        files.setdefault(path, set()).add(int(stage))
    return files


def is_build_folder(path):
    parts = PurePosixPath(path).parts
    return len(parts) >= 2 and parts[0].casefold() == 'game' and parts[1].casefold() == 'buildfolder'


def resolve_tag_side(repo, conflicts):
    """Retain stage 2; its absence means tag side deleted or never had the path."""
    protected = []
    for path, stages in conflicts.items():
        if is_build_folder(path):
            protected.append(path)
            continue
        # The literal pathspec environment avoids wildcard and pathspec-magic expansion.
        literal = ':(literal)' + path
        if 2 in stages:
            command(repo, 'checkout', '--ours', '--', literal)
            command(repo, 'add', '--', literal)
        else:
            command(repo, 'rm', '-f', '--ignore-unmatch', '--', literal)
    return protected
