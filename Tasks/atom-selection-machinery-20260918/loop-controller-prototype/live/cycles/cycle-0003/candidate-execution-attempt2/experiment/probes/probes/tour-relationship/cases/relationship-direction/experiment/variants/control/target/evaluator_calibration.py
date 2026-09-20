"""Frozen evaluator calibration before candidate execution."""
import copy
import hashlib
import json
import math
import re
from pathlib import Path

CALIBRATION_FIELDS = {'calibration'}
SECTION_KEYS = ['calibration']


def normalize_calibration(record, base):
    if not isinstance(record, dict) or set(record) != {'path','sha256'}:
        raise ValueError('calibration must contain exactly path and sha256')
    if not isinstance(record['path'], str) or not record['path']:
        raise ValueError('calibration.path must name a frozen calibration JSON file')
    value=copy.deepcopy(record)
    path=Path(record['path'])
    value['path']=str((path if path.is_absolute() else Path(base)/path).absolute())
    return value


def validate(record, metrics, assessment, spec_path):
    record=normalize_calibration(record,Path(spec_path).parent)
    path=Path(record['path'])
    if path.is_symlink() or not path.is_file():
        raise ValueError('calibration.path must be an existing regular unlinked JSON file')
    payload=path.read_bytes()
    if hashlib.sha256(payload).hexdigest()!=record['sha256']:
        raise ValueError('calibration SHA-256 differs from the frozen declaration; restore the recorded cases')
    document=json.loads(payload)
    if not isinstance(document,dict) or set(document)!={'schema_version','cases'} or type(document['schema_version']) is not int or document['schema_version']!=1:
        raise ValueError('calibration JSON must contain schema_version integer 1 and cases')
    cases=document['cases']
    if not isinstance(cases,list) or len(cases)<2:
        raise ValueError('calibration requires at least two positive and negative cases')
    names={metric['name'] for metric in metrics}
    seen=set(); coverage={name:set() for name in names}
    for index,case in enumerate(cases):
        label=f'calibration case {index}'
        if not isinstance(case,dict) or set(case)!={'id','outcome','expected_metrics'}:
            raise ValueError(f'{label} must contain exactly id, outcome, expected_metrics')
        identity=case['id']
        if not isinstance(identity,str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}',identity) or identity in seen:
            raise ValueError(f'{label} id must be unique lowercase identity')
        seen.add(identity)
        outcome=case['outcome']
        if not isinstance(outcome,dict) or any(field not in outcome for field in assessment['output_fields']):
            raise ValueError(f'{label} {identity!r} outcome must contain every selected raw-output field')
        scores=case['expected_metrics']
        if not isinstance(scores,dict) or set(scores)!=names:
            raise ValueError(f'{label} {identity!r} expected_metrics must contain exactly {sorted(names)}')
        for name,value in scores.items():
            if type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=1:
                raise ValueError(f'{label} {identity!r} expected metric {name!r} must be finite between zero and one')
            coverage[name].add(value)
    missing=[name for name,values in coverage.items() if not {0,1}.issubset(values)]
    if missing:
        raise ValueError(f'calibration must include both zero and one expected scores for metrics {missing}; add negative and positive controls')
    return {'bytes':payload,'document':document,'sha256':record['sha256']}


def candidate_rows(document):
    return [{'variant_id':case['id'],'eligible':True,'status':'completed','exit_code':0,
             'duration_ms':0,'timed_out':False,'outcome':copy.deepcopy(case['outcome']),
             'result_sha256':None,'stdout_sha256':None,'stderr_sha256':None,'telemetry_sha256':None}
            for case in document['cases']]


def verify_scores(document, scores):
    for case in document['cases']:
        actual=scores.get(case['id'])
        if actual!=case['expected_metrics']:
            raise ValueError(f"evaluator calibration case {case['id']!r} disagrees with independent expectations: expected {case['expected_metrics']!r}, observed {actual!r}; correct the evaluator before executing candidates")
