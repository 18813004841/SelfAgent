import json, sys, time
from pathlib import Path
sys.path.insert(0, 'Tools/code-review-agent')
from code_review.model_service import LocalModelClient
from code_review.pipeline import MODEL_OUTPUT_CONTRACT
p=Path('Tools/code-review-agent/data/koa-client-code-master/reports/koa-client-code-master-0044/model-input-006.md')
content=p.read_text(encoding='utf-8')
messages=[{'role':'system','content':'你是 Unity C# 代码审查器。'+MODEL_OUTPUT_CONTRACT},{'role':'user','content':content}]
started=time.time()
try:
    client=LocalModelClient(timeout=30, max_output_tokens=2000)
    result=client.complete(messages)
    print(json.dumps({'status':'ok','elapsed':round(time.time()-started,2),'length':len(result),'preview':result[:1000]},ensure_ascii=False))
except Exception as exc:
    print(json.dumps({'status':'error','elapsed':round(time.time()-started,2),'type':type(exc).__name__,'error':str(exc)},ensure_ascii=False))
