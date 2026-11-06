from __future__ import annotations
from fnmatch import fnmatch
from pathlib import Path

def discover(root: Path):
    result=[]
    for name in ('AGENTS.md','README.md','CONTRIBUTING.md'):
        path=root/name
        if path.is_file(): result.append(path)
    result.extend(sorted(root.glob('skills/**/SKILL.md')))
    result.extend(sorted(root.glob('.skills/**/SKILL.md')))
    return list(dict.fromkeys(result))

def load_matching(root: Path, files, skill_paths=None):
    configured=[]
    for item in skill_paths or []:
        path=Path(item).expanduser()
        if not path.is_absolute(): path=(root/path).resolve()
        candidates=[path] if path.is_file() else [path/'SKILL.md', *sorted(path.glob('**/SKILL.md'))]
        configured.extend(candidate for candidate in candidates if candidate.is_file())
    result=[]
    marker='## '+chr(36866)+chr(29992)+chr(33539)+chr(22260)
    for path in list(dict.fromkeys([*configured,*discover(root)])):
        text=path.read_text(encoding='utf-8', errors='replace')
        scope=text.split(marker,1)[1].split('##',1)[0] if marker in text else ''
        patterns=[line.strip() for line in scope.splitlines() if line.strip()]
        normalized=[item.replace('\\','/') for item in files]
        if patterns and not any(fnmatch(file_path, pattern) for pattern in patterns for file_path in normalized):
            continue
        try: label=str(path.relative_to(root))
        except ValueError: label=str(path)
        result.append({'path':label,'content':text})
    return result
