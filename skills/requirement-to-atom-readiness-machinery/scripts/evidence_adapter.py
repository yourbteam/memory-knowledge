"""Code-owned evidence and graph wire contracts; schemas do not certify readiness."""
import argparse
import json

MANIFEST_FIELDS = ('schema_version', 'kind', 'requirements_handoff_sha256', 'source_files',
                   'requirement_bindings', 'evidence', 'conditions', 'edges')
SOURCE_FIELDS = ('id', 'path', 'sha256', 'size')
BINDING_FIELDS = ('alias', 'requirement_id', 'legacy_document_source_id', 'legacy_ordinal',
                  'legacy_exact_text', 'current_exact_text', 'mapping_proof_source_id')
EVIDENCE_FIELDS = ('evidence_id', 'source_object_sha256', 'origin', 'capture_method',
                   'captured_at_utc', 'claim', 'limitations', 'affected_requirement_ids',
                   'required_maturity', 'freshness_rule', 'access_receipt',
                   'reproduction_receipt', 'model_share_authorization', 'sensitivity_class')
CONDITION_FIELDS = ('condition_id', 'resolution_class', 'source_id', 'source_quote',
                    'requirement_ids', 'recovery_condition', 'dependencies')
EDGE_FIELDS = ('type', 'source', 'target')
GRAPH_FIELDS = ('schema_version', 'nodes', 'edges', 'conditions')
NODE_FIELDS = ('id', 'type', 'record')
QUEUE_FIELDS = ('condition_id', 'node_id', 'blocking_class', 'dependency_layer',
                'requirement_ordinal', 'source_ordinal', 'recovery_condition')
NODE_TYPES = ('requirement', 'evidence', 'authority_decision', 'contradiction', 'verification', 'atom_candidate')
EDGE_TYPES = ('supports', 'refutes', 'requires', 'governed-by', 'conflicts-with', 'verified-by', 'maps-to-atom', 'precedes')
BLOCKING_CLASSES = ('integrity', 'mandatory-evidence', 'contradiction', 'semantic',
                    'research', 'planning', 'verification', 'owner')
RESOLUTION_CLASSES = ('deterministic-blocker', 'semantic-check', 'owner-decision',
                      'contradiction', 'direct-research', 'direct-planning', 'verification')
FITNESS_FIELDS = ('present', 'hash_valid', 'accessible_at_capture', 'current',
                  'reproducible', 'authorized_for_declared_use', 'fit')
SHA_PATTERN = r'^[0-9a-f]{64}$'


def closed(fields, properties):
    return {'type': 'object', 'additionalProperties': False, 'required': list(fields), 'properties': properties}


def array(item, minimum=0):
    return {'type': 'array', 'items': item, 'minItems': minimum, 'uniqueItems': True}


SEMANTIC_FAMILIES = ('evidence-bearing', 'evidence-sufficiency', 'dependency-discovery',
                     'contradiction-assessment', 'verification-adequacy', 'atom-cohesion',
                     'owner-question-formulation')
SEMANTIC_FIELDS = ('family', 'subject_ids', 'evidence_refs', 'criteria', 'dependency_ids',
                   'choices', 'answer_type', 'candidate', 'required_maturity')


def semantic_schema():
    text = {'type': 'string', 'minLength': 1, 'maxLength': 8192, 'pattern': r'\S'}
    return closed(SEMANTIC_FIELDS, {
        'family': {'enum': list(SEMANTIC_FAMILIES)},
        'required_maturity': {'enum': ['current-system', 'future-system', 'not-applicable']},
        'subject_ids': array(text, 1),
        'evidence_refs': array(closed(('evidence_id', 'quote'), {'evidence_id': text, 'quote': text}), 1),
        'criteria': array(closed(('criterion_id', 'source_object_sha256', 'quote'), {
            'criterion_id': text, 'source_object_sha256': {'type': 'string', 'pattern': SHA_PATTERN}, 'quote': text})),
        'dependency_ids': array(text),
        'choices': array(closed(('choice_id', 'label'), {'choice_id': text, 'label': text})),
        'answer_type': {'enum': ['not-applicable', 'enum-choice', 'free-text']},
        'candidate': {'anyOf': [{'type': 'null'}, closed(
            ('outcome', 'boundaries', 'prerequisites', 'requirement_ids', 'case_ids'), {
                'outcome': text, 'boundaries': array(text, 1), 'prerequisites': array(text),
                'requirement_ids': array(text, 1), 'case_ids': array(text, 1)})]}})


def validate_semantic(spec, row, requirements, evidence, sources, aliases, condition_ids):
    """Bind an explicit obligation to admitted identities. Never infer it from prose."""
    validate(spec, semantic_schema())
    family = spec['family']
    label = 'interview ' + row['condition_id']
    def require(ok, message):
        if not ok:
            raise EvidenceRefused(label + ': ' + message)
    require(row['resolution_class'] == ('owner-decision' if family == 'owner-question-formulation' else 'semantic-check'),
            'family ' + family + ' requires an explicit matching semantic-check or owner-decision condition')
    for field in ('subject_ids', 'evidence_refs', 'criteria', 'dependency_ids', 'choices'):
        require(len(spec[field]) <= 256, field + ' exceeds 256 items; split the declared obligation before preparation')
    require((spec['required_maturity'] != 'not-applicable') == (family == 'evidence-sufficiency'),
            'evidence-sufficiency requires explicit current-system or future-system maturity; other families use not-applicable')
    subjects = [aliases.get(i, i) for i in spec['subject_ids']]
    require(len(set(subjects)) == len(subjects) and all(i in requirements for i in subjects),
            'subject_ids must be distinct sealed requirement identities; foreign or duplicate identity supplied')
    require(set(subjects) <= {aliases.get(i, i) for i in row['requirement_ids']},
            'subject_ids exceed the requirements affected by this condition; bind the exact affected set')
    if family in ('evidence-bearing', 'evidence-sufficiency', 'dependency-discovery'):
        require(len(subjects) == 1, family + ' requires exactly one subject requirement')
    if family == 'contradiction-assessment':
        require(len(subjects) == 2, 'contradiction-assessment requires two distinct registered requirement claims')
    selected = [ref['evidence_id'] for ref in spec['evidence_refs']]
    require(len(set(selected)) == len(selected), 'evidence_refs repeats an evidence_id; select each once')
    for ref in spec['evidence_refs']:
        require(ref['evidence_id'] in evidence, 'foreign evidence_id ' + ref['evidence_id'] + '; supply an admitted evidence record')
        record = evidence[ref['evidence_id']]
        raw = sources.get(record['source_object_sha256'])
        require(raw is not None, 'evidence ' + ref['evidence_id'] + ' lacks its source object; admit its exact bytes')
        require(ref['quote'].encode('utf-8') in raw, 'quote for ' + ref['evidence_id'] + ' is absent; copy exact source bytes')
        require(bool(set(subjects) & set(record['affected_requirement_ids'])),
                'evidence ' + ref['evidence_id'] + ' has no affected subject; provide a declared subject binding')
    if family == 'evidence-bearing':
        require(len(selected) == 1, 'evidence-bearing requires exactly one evidence item')
    if family == 'contradiction-assessment':
        require(len(selected) == 2, 'contradiction-assessment requires the two source evidence anchors')
    criteria = [c['criterion_id'] for c in spec['criteria']]
    require(len(set(criteria)) == len(criteria), 'criteria repeats an identity; provide each once')
    require(bool(criteria) == (family in ('evidence-sufficiency', 'verification-adequacy')),
            'criteria must be nonempty for sufficiency/adequacy and empty for other families')
    for criterion in spec['criteria']:
        require(criterion['source_object_sha256'] in {evidence[i]['source_object_sha256'] for i in selected},
                'criterion ' + criterion['criterion_id'] + ' has no selected evidence metadata; select its evidence record before sharing its quote')
        raw = sources.get(criterion['source_object_sha256'])
        require(raw is not None and criterion['quote'].encode('utf-8') in raw,
                'criterion ' + criterion['criterion_id'] + ' has a foreign hash or absent quote; bind exact admitted bytes')
    dependencies = [aliases.get(i, i) for i in spec['dependency_ids']]
    require(len(set(dependencies)) == len(dependencies) and all(i in requirements or i in condition_ids for i in dependencies),
            'dependency_ids contains duplicate or foreign IDs; use distinct admitted requirements or conditions')
    require(not set(dependencies) & set(subjects), 'dependency_ids contains the subject itself; remove the self-edge')
    require(family == 'dependency-discovery' or not dependencies, 'only dependency-discovery may list dependency candidates')
    choices = [c['choice_id'] for c in spec['choices']]
    require(len(set(choices)) == len(choices), 'choices repeats a choice_id; list each once')
    if family == 'owner-question-formulation':
        require(spec['answer_type'] in ('enum-choice', 'free-text'), 'owner question needs enum-choice or free-text answer_type')
        require(bool(choices) == (spec['answer_type'] == 'enum-choice'), 'enum-choice requires a complete nonempty choice set; free-text requires no choices')
    else:
        require(spec['answer_type'] == 'not-applicable' and not choices, 'non-owner interview cannot define an owner answer or choices')
    candidate = spec['candidate']
    require((candidate is not None) == (family == 'atom-cohesion'), 'candidate is required only for atom-cohesion and must otherwise be null')
    if candidate is not None:
        require(set(candidate['requirement_ids']) == set(subjects), 'candidate requirement_ids differ from the complete subject set')
        require(all(i in requirements or i in condition_ids for i in candidate['prerequisites']), 'candidate prerequisites contain an unregistered identity')
    return {**spec, 'subject_ids': subjects, 'dependency_ids': dependencies}


def definitions():
    text = {'type': 'string', 'minLength': 1, 'pattern': r'\S'}
    digest = {'$ref': '#/$defs/sha256'}
    source = closed(SOURCE_FIELDS, {'id': text, 'path': {'type':'string','pattern':'^/'},
                                   'sha256': digest, 'size': {'type':'integer','minimum':0}})
    receipt = closed(('source_id','pointer','outcome'), {'source_id':text, 'pointer':{'type':'string'},
                     'outcome':{'enum':['accessible','inaccessible','missing','reproduced','not-reproducible','not-yet-applicable']}})
    freshness = closed(('kind','max_age_seconds'), {'kind':{'enum':['immutable','max-age']},
                       'max_age_seconds':{'type':'integer','minimum':0}})
    sharing = closed(('use','receipt_source_id'), {'use':{'enum':['local-only','model-authorized','denied']},
                     'receipt_source_id':{'type':['string','null']}})
    evidence = closed(EVIDENCE_FIELDS, {
        'evidence_id':text, 'source_object_sha256':{'anyOf':[digest,{'type':'null'}]},
        'origin':text, 'capture_method':text, 'captured_at_utc':text, 'claim':text,
        'limitations':array(text), 'affected_requirement_ids':array(text,1),
        'required_maturity':{'enum':['current-system','future-system']}, 'freshness_rule':freshness,
        'access_receipt':receipt, 'reproduction_receipt':receipt,
        'model_share_authorization':sharing, 'sensitivity_class':{'enum':['public','internal','restricted','secret']}})
    condition = closed(CONDITION_FIELDS, {'condition_id':text,'resolution_class':{'enum':list(RESOLUTION_CLASSES)},
                       'source_id':text,'source_quote':text,'requirement_ids':array(text,1),
                       'recovery_condition':text,'dependencies':array(text)})
    condition = {'oneOf': [condition, closed(CONDITION_FIELDS + ('interview',), {**condition['properties'], 'interview': semantic_schema()})]}
    binding = closed(BINDING_FIELDS, {'alias':text,'requirement_id':text,'legacy_document_source_id':text,
                     'legacy_ordinal':{'type':'integer','minimum':1},'legacy_exact_text':text,
                     'current_exact_text':text,'mapping_proof_source_id':{'type':['string','null']}})
    edge = closed(EDGE_FIELDS, {'type':{'enum':list(EDGE_TYPES)},'source':text,'target':text})
    fitness = closed(FITNESS_FIELDS,{key:{'type':'boolean'} for key in FITNESS_FIELDS})
    anchor = closed(('piece_id','sha256','quote'),{'piece_id':text,'sha256':digest,'quote':text})
    requirement = closed(('requirement_id','ordinal','exact_text','source_anchors','maturity','disposition'),
        {'requirement_id':text,'ordinal':{'type':'integer','minimum':1},'exact_text':text,'source_anchors':array(anchor,1),
         'maturity':{'enum':['unassessed','current-system','future-system']},'disposition':{'enum':['unassessed','blocked','mapped']}})
    evidence_node = closed(('evidence','fitness'),{'evidence':evidence,'fitness':fitness})
    authority = closed(('owner','question','answer_contract','answer'),{'owner':{'const':'owner'},'question':text,
                        'answer_contract':{'const':'owner-only-pending'},'answer':{'type':'null'}})
    contradiction = closed(('claim_ids','source_anchors','state','resolution_authority'),
        {'claim_ids':array(text,2),'source_anchors':array(text,1),'state':{'enum':['open','resolved']},
         'resolution_authority':{'enum':['owner','semantic']}})
    verification = closed(('observable','success_cases','rejection_cases','execution_route','independence_rule','status'),
        {'observable':text,'success_cases':array(text),'rejection_cases':array(text),'execution_route':text,
         'independence_rule':{'enum':['independent','producer-only','unassessed']},'status':{'enum':['pending','blocked','verified']}})
    atom = closed(('outcome','boundaries','prerequisites','requirement_ids','case_ids'),
        {'outcome':text,'boundaries':array(text,1),'prerequisites':array(text),'requirement_ids':array(text,1),'case_ids':array(text,1)})
    verification = {'oneOf': [verification, closed(tuple(verification['required']) + ('interview',), {**verification['properties'], 'interview': semantic_schema()})]}
    authority = {'oneOf': [authority, closed(tuple(authority['required']) + ('interview',), {**authority['properties'], 'interview': semantic_schema()})]}
    records = [requirement,evidence_node,authority,contradiction,verification,atom]
    node = {'oneOf':[closed(NODE_FIELDS,{'id':text,'type':{'const':kind},'record':record}) for kind,record in zip(NODE_TYPES,records)]}
    queue = closed(QUEUE_FIELDS,{'condition_id':text,'node_id':text,'blocking_class':{'enum':list(BLOCKING_CLASSES)},
        'dependency_layer':{'type':'integer','minimum':0},'requirement_ordinal':{'type':'integer','minimum':1},
        'source_ordinal':{'type':'integer','minimum':0},'recovery_condition':text})
    return {'sha256':{'type':'string','pattern':SHA_PATTERN,'minLength':64,'maxLength':64},
            'source':source,'binding':binding,'evidence':evidence,'condition':condition,'edge':edge,'node':node,'queue_item':queue}


def evidence_schema():
    ref=lambda name:{'$ref':'#/$defs/'+name}
    schema=closed(MANIFEST_FIELDS,{'schema_version':{'const':1,'type':'integer'},
        'kind':{'enum':['evidence','telemetry','blockers']},'requirements_handoff_sha256':ref('sha256'),
        'source_files':array(ref('source')),'requirement_bindings':array(ref('binding')),
        'evidence':array(ref('evidence')),'conditions':array(ref('condition')),'edges':array(ref('edge'))})
    schema.update({'$schema':'https://json-schema.org/draft/2020-12/schema','title':'Readiness evidence manifest v1','$defs':definitions()})
    return schema


def graph_schema():
    schema=closed(GRAPH_FIELDS,{'schema_version':{'const':1,'type':'integer'},'nodes':array({'$ref':'#/$defs/node'}),
        'edges':array({'$ref':'#/$defs/edge'}),'conditions':array({'$ref':'#/$defs/queue_item'})})
    schema.update({'$schema':'https://json-schema.org/draft/2020-12/schema','title':'Readiness typed graph v1','$defs':definitions()})
    return schema


def main():
    parser=argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('command',choices=['schema'])
    parser.add_argument('contract',choices=['evidence','graph'])
    args=parser.parse_args()
    print(json.dumps(evidence_schema() if args.contract=='evidence' else graph_schema(),sort_keys=True,indent=2))
    return 0



# Atom 6: deterministic admission over controller-supplied frozen bytes only.
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

ENDPOINTS = {
    'supports': (('evidence',), ('requirement','verification')),
    'refutes': (('evidence',), ('requirement','verification')),
    'requires': (NODE_TYPES, NODE_TYPES),
    'governed-by': (('requirement','evidence','verification','atom_candidate'), ('authority_decision',)),
    'conflicts-with': (('evidence',), ('evidence',)),
    'verified-by': (('requirement','evidence','atom_candidate'), ('verification',)),
    'maps-to-atom': (('requirement',), ('atom_candidate',)),
    'precedes': (('atom_candidate',), ('atom_candidate',)),
}
RESOLUTION_TO_CLASS = dict(zip(RESOLUTION_CLASSES, ('mandatory-evidence','semantic','owner','contradiction','research','planning','verification')))


class EvidenceRefused(ValueError):
    pass


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def validate(value, schema, root=None, label='manifest'):
    """Implement only the finite JSON-Schema vocabulary emitted by these contracts."""
    root=schema if root is None else root
    if '$ref' in schema:
        return validate(value,root['$defs'][schema['$ref'].split('/')[-1]],root,label)
    for union in ('anyOf','oneOf'):
        if union in schema:
            accepted=0
            for choice in schema[union]:
                try:validate(value,choice,root,label);accepted+=1
                except EvidenceRefused:pass
            if (union=='oneOf' and accepted!=1) or (union=='anyOf' and not accepted):
                raise EvidenceRefused(label+': value does not match the declared typed alternatives; supply the exact contract')
            return
    types={'object':dict,'array':list,'string':str,'integer':int,'boolean':bool,'null':type(None)}
    if 'type' in schema:
        kinds=schema['type'] if isinstance(schema['type'],list) else [schema['type']]
        if not any(type(value) is types[k] for k in kinds):raise EvidenceRefused(label+': wrong value type')
    if 'const' in schema and (type(value) is not type(schema['const']) or value!=schema['const']):raise EvidenceRefused(label+': wrong fixed value')
    if 'enum' in schema and value not in schema['enum']:raise EvidenceRefused(label+': unsupported enum')
    if type(value) is dict:
        if set(value)!=set(schema.get('required',value)) or (schema.get('additionalProperties') is False and set(value)-set(schema['properties'])):raise EvidenceRefused(label+': missing or unknown field')
        for key,item in value.items():validate(item,schema['properties'][key],root,label+'.'+key)
    if type(value) is list:
        if len(value)<schema.get('minItems',0):raise EvidenceRefused(label+': incomplete list')
        if schema.get('uniqueItems') and len({canonical(x) for x in value})!=len(value):raise EvidenceRefused(label+': duplicate list member')
        for i,item in enumerate(value):validate(item,schema['items'],root,f'{label}[{i}]')
    if type(value) is str:
        if len(value)<schema.get('minLength',0) or len(value)>schema.get('maxLength',float('inf')):raise EvidenceRefused(label+': invalid string length')
        if 'pattern' in schema and re.search(schema['pattern'],value) is None:raise EvidenceRefused(label+': invalid string value')
    if type(value) is int and value<schema.get('minimum',value):raise EvidenceRefused(label+': below declared minimum')


def pointer(value, path):
    if path=='':return value
    if not path.startswith('/'):raise EvidenceRefused('receipt pointer must be an explicit JSON pointer')
    for token in path[1:].split('/'):
        token=token.replace('~1','/').replace('~0','~')
        value=value[int(token)] if type(value) is list else value[token]
    return value


def timestamp(value):
    parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
    if parsed.tzinfo is None or parsed.utcoffset().total_seconds()!=0:raise EvidenceRefused('capture time must explicitly use UTC')
    return parsed


def fitness(record, sources, as_of):
    object_hash=record['source_object_sha256']
    present=object_hash is not None and any(digest(raw)==object_hash for raw in sources.values())
    def receipt(name,outcome):
        item=record[name]
        try:
            raw=pointer(json.loads(sources[item['source_id']]),item['pointer'])
            return item['outcome']==outcome and raw['outcome']==outcome and raw['object_sha256']==object_hash
        except (KeyError,ValueError,TypeError,IndexError):return False
    age=(timestamp(as_of)-timestamp(record['captured_at_utc'])).total_seconds()
    rule=record['freshness_rule']
    current=age>=0 and (rule['kind']=='immutable' or age<=rule['max_age_seconds'])
    reproduction=receipt('reproduction_receipt','reproduced')
    if record['required_maturity']=='future-system' and receipt('reproduction_receipt','not-yet-applicable'):
        item=record['reproduction_receipt'];proof=pointer(json.loads(sources[item['source_id']]),item['pointer'])
        reproduction=all(type(proof.get(k)) is list and proof[k] and all(type(x) is str and x.strip() for x in proof[k]) for k in ['constraints','success_cases','rejection_cases']) and bool(proof.get('execution_route'))
    sharing=record['model_share_authorization']
    authorized=sharing['use']!='denied' and record['sensitivity_class']!='secret'
    # Fitness admits evidence for LOCAL preparation only. A model-authorized label
    # is not permission: the launcher separately checks exact payload authority.
    # Local-only and denied evidence remain forbidden at that transmission boundary.
    result={'present':present,'hash_valid':present,'accessible_at_capture':receipt('access_receipt','accessible'),
            'current':current,'reproducible':reproduction,'authorized_for_declared_use':authorized}
    result['fit']=all(result.values());return result


def binding_map(bindings, requirements, sources, current_document_sha256):
    aliases={};targets=set();by_id={r['requirement_id']:r for r in requirements}
    by_hash={digest(raw):raw for raw in sources.values()}
    for row in bindings:
        alias=row['alias'];target=row['requirement_id']
        if alias in aliases or target in targets or target not in by_id:raise EvidenceRefused('binding: duplicate or foreign requirement identity')
        legacy=sources[row['legacy_document_source_id']].decode('utf-8')
        paragraphs=re.findall(r'^\d+\. (.*?)  $',legacy,re.M)
        if row['legacy_ordinal']>len(paragraphs) or paragraphs[row['legacy_ordinal']-1]!=row['legacy_exact_text']:raise EvidenceRefused('binding: legacy text or ordinal differs from its frozen source')
        if row['current_exact_text']!=by_id[target]['exact_text']:raise EvidenceRefused('binding: current text differs from the sealed requirement ID')
        if row['legacy_exact_text']!=row['current_exact_text']:
            proof=json.loads(sources[row['mapping_proof_source_id']]);payload=json.loads(by_hash[proof['payload_sha256']])
            if [s['sha256'] for s in payload['sources']] != [digest(sources[row['legacy_document_source_id']]),current_document_sha256]:raise EvidenceRefused('binding: interview source hashes differ from the legacy and sealed current documents')
            if proof['verdict']!='confirmed' or [s['seat'] for s in proof['seats']]!=[1,2]:raise EvidenceRefused('binding: require two distinct preserved blind seats')
            pair=next(p for p in payload['pairs'] if p['legacy_alias']==alias)
            if pair['legacy_exact_text']!=row['legacy_exact_text'] or pair['current_exact_text']!=row['current_exact_text'] or pair['current_ordinal']!=by_id[target]['ordinal']:raise EvidenceRefused('binding: mapping proof is for another text pair')
            for seat in proof['seats']:
                if json.loads(by_hash[seat['response_sha256']])!=seat['response']:raise EvidenceRefused('binding: blind response bytes differ')
                answer=next(a for a in seat['response']['answers'] if a['legacy_alias']==alias)
                if answer['current_ordinal']!=by_id[target]['ordinal'] or answer['verdict']!='equivalent' or not answer['reason'].strip():raise EvidenceRefused('binding: missing or disagreeing blind mapping')
                for quote,text in [('legacy_quote','legacy_exact_text'),('current_quote','current_exact_text')]:
                    if not answer[quote].strip() or answer[quote] not in row[text]:raise EvidenceRefused('binding: ungrounded mapping quote')
        elif row['mapping_proof_source_id'] is not None:raise EvidenceRefused('binding: exact-text mapping must not claim an unnecessary semantic proof')
        aliases[alias]=target;targets.add(target)
    return aliases


def verify_edges(nodes, edges):
    kinds={n['id']:n['type'] for n in nodes};seen=set();dependencies={n:[] for n in kinds}
    for edge in edges:
        source,target,kind=edge['source'],edge['target'],edge['type'];key=(kind,source,target)
        if key in seen:raise EvidenceRefused('graph: duplicate edge; supply one shared dependency')
        seen.add(key)
        if source not in kinds or target not in kinds:raise EvidenceRefused('graph: foreign endpoint; reference registered node IDs')
        if source==target:raise EvidenceRefused('graph: self-dependency is forbidden')
        allowed=ENDPOINTS[kind]
        if kinds[source] not in allowed[0] or kinds[target] not in allowed[1]:raise EvidenceRefused('graph: forbidden endpoint types; correct the typed edge')
        if kind in ('requires','precedes'):dependencies[source].append(target)
    visiting=set();layers={}
    def depth(node):
        if node in visiting:raise EvidenceRefused('graph: dependency cycle; remove the cyclic dependency before admission')
        if node in layers:return layers[node]
        visiting.add(node);layers[node]=max((depth(n)+1 for n in dependencies[node]),default=0);visiting.remove(node);return layers[node]
    for node in kinds:depth(node)
    return layers


def build_graph(manifests, upstream, read, as_of, parse_blockers=None):
    """Admit explicit manifests; never infer conditions from filenames or run probes."""
    requirements=upstream['requirements'];known={r['requirement_id']:r for r in requirements}
    nodes=[{'id':r['requirement_id'],'type':'requirement','record':{**r,'maturity':'unassessed','disposition':'blocked'}} for r in requirements]
    sources={};source_rows={};bindings=[];evidence=[];conditions=[];edges=[];raw_blockers=[]
    for manifest in manifests:
        validate(manifest,evidence_schema())
        if manifest['requirements_handoff_sha256']!=upstream['handoff_sha256']:raise EvidenceRefused('manifest: wrong sealed Requirements handoff')
        for row in manifest['source_files']:
            if row['id'] in sources:raise EvidenceRefused('manifest: duplicate source identity')
            raw=read(Path(row['path']),row['sha256'])
            if len(raw)!=row['size']:raise EvidenceRefused('manifest: source size differs')
            sources[row['id']]=raw;source_rows[row['id']]=row
            if manifest['kind']=='blockers':raw_blockers.append((row['id'],raw))
        bindings.extend(manifest['requirement_bindings']);evidence.extend(manifest['evidence']);conditions.extend(manifest['conditions']);edges.extend(manifest['edges'])
    aliases=binding_map(bindings,requirements,sources,upstream['current_document_sha256'])
    def resolve(ids):
        result=[aliases.get(i,i) for i in ids]
        if len(result)!=len(set(result)) or any(i not in known for i in result):raise EvidenceRefused('record: duplicate or foreign requirement identity; supply an explicit checked binding')
        return result
    pending=[];condition_nodes={};used_evidence=set()
    def register_condition(row, ordinal):
        identity=row['condition_id']
        if identity in condition_nodes:raise EvidenceRefused('condition: duplicate identity')
        requirement_ids=resolve(row['requirement_ids'])
        if row['source_id'] not in sources:raise EvidenceRefused(f'condition {identity}: source {row["source_id"]!r} is absent; include its hash-bound source descriptor')
        raw=sources[row['source_id']].decode('utf-8')
        if ' '.join(row['source_quote'].split()) not in ' '.join(raw.split()):raise EvidenceRefused('condition: source quote absent from declared bytes')
        node_id='condition-'+digest(canonical(row))[:24];condition_nodes[identity]=node_id
        owner=row['resolution_class']=='owner-decision'
        record=({'owner':'owner','question':row['recovery_condition'],'answer_contract':'owner-only-pending','answer':None} if owner else
                {'observable':row['source_quote'],'success_cases':[],'rejection_cases':[],'execution_route':row['recovery_condition'],'independence_rule':'unassessed','status':'blocked'})
        nodes.append({'id':node_id,'type':'authority_decision' if owner else 'verification','record':record})
        for rid in requirement_ids:edges.append({'type':'governed-by' if owner else 'verified-by','source':rid,'target':node_id})
        pending.append({'condition_id':identity,'node_id':node_id,'blocking_class':RESOLUTION_TO_CLASS[row['resolution_class']],
            'dependency_layer':0,'requirement_ordinal':min(known[r]['ordinal'] for r in requirement_ids),'source_ordinal':ordinal,'recovery_condition':row['recovery_condition']})
    for ordinal,row in enumerate(conditions):register_condition(row,ordinal)
    for row in conditions:
        for dependency in row['dependencies']:
            if dependency not in condition_nodes:raise EvidenceRefused('condition: unknown dependency')
            edges.append({'type':'requires','source':condition_nodes[row['condition_id']],'target':condition_nodes[dependency]})
    for ordinal,record in enumerate(evidence,len(conditions)):
        if record['evidence_id'] in used_evidence:raise EvidenceRefused('evidence: duplicate identity')
        used_evidence.add(record['evidence_id']);record={**record,'affected_requirement_ids':resolve(record['affected_requirement_ids'])}
        checked=fitness(record,sources,as_of);node_id='evidence-'+digest(canonical(record))[:24]
        nodes.append({'id':node_id,'type':'evidence','record':{'evidence':record,'fitness':checked}})
        for rid in record['affected_requirement_ids']:edges.append({'type':'supports','source':node_id,'target':rid})
        if not checked['fit']:
            failures=[k for k,v in checked.items() if k!='fit' and not v]
            pending.append({'condition_id':record['evidence_id'],'node_id':node_id,'blocking_class':'mandatory-evidence','dependency_layer':0,
                'requirement_ordinal':min(known[r]['ordinal'] for r in record['affected_requirement_ids']),'source_ordinal':ordinal,
                'recovery_condition':'Admit a new hash-bound evidence capture satisfying: '+', '.join(failures)})
    # A raw open occurrence cannot be erased by an unverified closed status or an omitted condition.
    for source_id,raw in raw_blockers:
        if parse_blockers is None:raise EvidenceRefused('blocker ledger: canonical lifecycle validator is required before admission')
        events=parse_blockers(raw)
        current={};occurrences={}
        for event in events:
            kind=event['event_type'];bid=event.get('blocker_id')
            if kind in ('pre_run_blocker_opened','blocker_opened','blocker_recurred'):
                current[bid]=event['occurrence_id'];occurrences[(bid,current[bid])]={'opening':event,'status':'open'}
            elif kind in ('pre_run_blocker_transitioned','blocker_transitioned') and bid in current:
                occurrences[(bid,current[bid])]['status']=event['to_status']
        for state in occurrences.values():
            if state['status'] in ('closed','non-gap'):continue
            event=state['opening']
            quote=event.get('evidence') or event.get('symptom')
            if not quote:raise EvidenceRefused('blocker ledger: missing opening evidence')
            if any(digest(sources[c['source_id']])==digest(raw) and c['source_quote']==quote and c['resolution_class']=='deterministic-blocker' for c in conditions):continue
            register_condition({'condition_id':'blocker-'+event['occurrence_id'],'resolution_class':'deterministic-blocker','source_id':source_id,
                'source_quote':quote,'requirement_ids':list(known),'recovery_condition':'Supply complete same-path verification and blocker closeout for '+event['occurrence_id'],'dependencies':[]},len(pending))
    # Resolve descriptors only after every evidence record and condition has been admitted.
    evidence_by_id={n['record']['evidence']['evidence_id']:n['record']['evidence'] for n in nodes if n['type']=='evidence'}
    source_by_hash={digest(raw):raw for raw in sources.values()}
    for row in conditions:
        if 'interview' in row:
            spec=validate_semantic(row['interview'],row,known,evidence_by_id,source_by_hash,aliases,set(condition_nodes))
            next(n for n in nodes if n['id']==condition_nodes[row['condition_id']])['record']['interview']=spec
    nodes.sort(key=lambda n:n['id']);edges.sort(key=lambda e:(e['type'],e['source'],e['target']))
    if len({n['id'] for n in nodes})!=len(nodes):raise EvidenceRefused('graph: node identity collision')
    layers=verify_edges(nodes,edges)
    for item in pending:item['dependency_layer']=layers[item['node_id']]
    pending.sort(key=lambda q:(BLOCKING_CLASSES.index(q['blocking_class']),q['dependency_layer'],q['requirement_ordinal'],q['source_ordinal'],q['node_id']))
    graph={'schema_version':1,'nodes':nodes,'edges':edges,'conditions':pending};validate(graph,graph_schema())
    return {'graph':graph,'graph_sha256':digest(canonical(graph)),'queue':pending,'next_action':pending[0] if pending else None,
            'status':'needs_owner' if pending and pending[0]['blocking_class']=='owner' else 'blocked','readiness':'not-assessed'}

if __name__=='__main__':
    raise SystemExit(main())
