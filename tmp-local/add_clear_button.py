from pathlib import Path
html = Path('workbench/machine-dashboard-server/web/pages/code-review.html')
lines = html.read_text(encoding='utf-8').splitlines()
button = '    <button type="button" id="review-clear-history">清空历史</button>'
if not any('review-clear-history' in line for line in lines):
    index = next(i for i, line in enumerate(lines) if 'review-stop' in line)
    lines.insert(index + 1, button)
    html.write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
print('html ok')
