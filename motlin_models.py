import motlin_lib
import json


def get_models(motlin_token, file_name):
    models = []
    with open(file_name, 'r') as file_handler:
        for model in json.load(file_handler):
            model_ids = {'flow_id': '', 'flow_slug': '', 'fields': {}}
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
                models.append(model_ids)
                continue
            for field in model['fields']:
                field_id = motlin_lib.get_item_id(
                    motlin_token,
                    'fields',
                    slug=model['flow']['slug'],
                    field='slug',
                    value=field['slug']
                )
                if field_id:
                    model_ids['fields'][field['name']] = field_id
                    continue
                model_ids['fields'][field['name']] = motlin_lib.add_new_field(motlin_token, flow_id, field)
            models.append(model_ids)
    return models
