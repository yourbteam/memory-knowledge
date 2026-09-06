"""Frozen quality qualification and comparison outcomes."""
import math

SELECTION_FIELDS = {'minimums'}
SECTION_KEYS = ['minimums']


def validate(selection, metrics, default=False):
    if selection is None:
        return {metric['name']: 1.0 for metric in metrics} if default else None
    if not isinstance(selection, dict) or set(selection) != SELECTION_FIELDS:
        raise ValueError('selection must contain exactly minimums')
    minimums = selection['minimums']
    if not isinstance(minimums, dict) or not minimums:
        raise ValueError('selection.minimums must name at least one essential metric')
    directions = {metric['name']:metric['direction'] for metric in metrics}
    for name, value in minimums.items():
        if name not in directions or directions[name] != 'maximize':
            raise ValueError(f'selection minimum {name!r} must name a declared maximize metric')
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError(f'selection minimum {name!r} must be finite numeric')
        if default and not 0 <= value <= 1:
            raise ValueError(f'observation minimum {name!r} must be between zero and one')
    return {name:float(value) for name,value in minimums.items()}


def failures(scores, minimums):
    return [{'metric':name,'actual':scores.get(name),'minimum':value}
            for name,value in (minimums or {}).items()
            if name not in scores or scores[name] < value]


def choose(rows, metrics, minimums):
    """Rows use variant_id, metrics, eligible; explicit prior qualified=False is retained."""
    for row in rows:
        unmet = failures(row['metrics'], minimums)
        row['qualification_failures'] = row.get('qualification_failures', []) + unmet
        row['qualified'] = bool(row['eligible'] and row.get('qualified', True) and not unmet)
    def key(row):
        return tuple(-row['metrics'][m['name']] if m['direction']=='maximize'
                     else row['metrics'][m['name']] for m in metrics)
    eligible = sorted((row for row in rows if row['qualified']), key=lambda row:(key(row),row['variant_id']))
    ranking = [{'rank':index,'variant_id':row['variant_id'],'metrics':row['metrics']}
               for index,row in enumerate(eligible,1)]
    if not eligible:
        return {'champion':None,'ranking':ranking,'selection_outcome':'no-qualified-candidate'}
    if minimums is not None and len(eligible)>1 and key(eligible[0])==key(eligible[1]):
        return {'champion':None,'ranking':ranking,'selection_outcome':'no-demonstrated-advantage'}
    return {'champion':eligible[0]['variant_id'],'ranking':ranking,'selection_outcome':'selected'}
