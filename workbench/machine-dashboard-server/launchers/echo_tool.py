#!/usr/bin/env python3
import argparse, json
p=argparse.ArgumentParser(); p.add_argument('--input', default='{}'); a=p.parse_args(); print(json.dumps({'ok': True, 'input': json.loads(a.input)}, ensure_ascii=False))
