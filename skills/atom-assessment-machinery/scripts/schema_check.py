"""Validate the small JSON-schema subset used by this skill."""
def validate(value, schema, root=None):
    root = schema if root is None else root
    if '$ref' in schema:
        ref = schema['$ref']
        if not ref.startswith('#/$defs/'):
            raise ValueError('Unsupported schema reference: ' + ref)
        return validate(value, root['$defs'][ref[len('#/$defs/'):]], root)
    kind = schema['type']
    if kind == 'object':
        if not isinstance(value, dict) or set(value) != set(schema['required']):
            raise ValueError('Object does not have the declared fields.')
        for key, item in value.items():
            validate(item, schema['properties'][key], root)
    elif kind == 'array':
        if not isinstance(value, list):
            raise ValueError('Expected a list.')
        for item in value:
            validate(item, schema['items'], root)
    elif kind == 'string':
        if not isinstance(value, str) or not value.strip():
            raise ValueError('Expected nonempty text.')
    else:
        raise ValueError('Unsupported schema type.')
    if 'enum' in schema and value not in schema['enum']:
        raise ValueError('Value is outside the declared choices.')
