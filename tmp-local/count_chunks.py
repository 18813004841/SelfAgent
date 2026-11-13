import collections, re, sys
from pathlib import Path
sys.path.insert(0, 'Tools/code-review-agent')
from code_review.pipeline import ReviewPipeline
p = Path('Tools/code-review-agent/data/koa-client-code-master/reports/koa-client-code-master-0043/changes.diff')
d = p.read_text(encoding='utf-8')
files = re.findall(r'^diff --git a/.+ b/(.+)$', d, re.M)
obj = object.__new__(ReviewPipeline)
kept = [f for f in files if obj.is_review_script(f)]
chunks = obj.split_diff(d, files)
counts = collections.Counter(x['files'][0] for x in chunks)
print('diff_files', len(files))
print('review_files', len(kept))
print('chunks', len(chunks))
print('multi', {k: v for k, v in counts.items() if v > 1})
print('skipped_non_cs', sum(not f.lower().endswith('.cs') for f in files))
print('skipped_outside', sum(f.lower().endswith('.cs') and not obj.is_review_script(f) for f in files))
