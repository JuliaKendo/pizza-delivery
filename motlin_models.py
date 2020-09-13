import motlin_lib


def get_models():
    models = []
    models.append(
        {
            'flow': {
                'name': 'Pizzeria',
                'slug': 'pizzeria',
                'description': 'Store addresses'
            },
            'fields': [
                {
                    'name': 'Address',
                    'description': 'Address',
                    'type': 'string'
                },
                {
                    'name': 'Alias',
                    'description': 'Alias',
                    'type': 'string'
                },
                {
                    'name': 'Longitude',
                    'description': 'Longitude',
                    'type': 'float'
                },
                {
                    'name': 'Latitude',
                    'description': 'Latitude',
                    'type': 'float'
                }
            ]
        }
    )
    return models


def initialize_model(motlin_token):
    model_ids = {'flow_id': '', 'flow_slug': '', 'fields': {}}
    models = get_models()

    for model in models:
        flow_id = motlin_lib.get_item_id(
            motlin_token,
            'flows',
            field='name',
            value=model['flow']['name']
        )
        if not flow_id:
            flow_id = motlin_lib.add_new_flow(
                motlin_token,
                model['flow']['name'],
                model['flow']['slug'],
                model['flow']['description']
            )
        if flow_id:
            model_ids['flow_id'], model_ids['flow_slug'] = flow_id, model['flow']['slug']
        else:
            return model_ids
        for field in model['fields']:
            field_id = motlin_lib.get_item_id(
                motlin_token,
                'fields',
                slug='pizzeria',
                field='name',
                value=field['name']
            )
            if field_id:
                model_ids['fields'][field['name']] = field_id
                continue
            model_ids['fields'][field['name']] = motlin_lib.add_new_field(motlin_token, flow_id, field)

    return model_ids
