"""Versioned project visual references with explicit first-frame or multi-image conditioning."""
from uuid import uuid4
from . import film, film_images, h3_joint_av_recipe as recipe
from .studio import StudioError, text
from .generation import utc_now

PREFIX = 'film.production-reference.'

def get(studio, project_id, identity, revision=None):
    film.project(studio, project_id)
    film._id(identity, 'reference')
    record = film._read(studio, PREFIX + identity + ('.revision.' + str(revision) if revision is not None else ''))
    if record['project_id'] != project_id:
        raise StudioError('Reference belongs to another project', 409)
    for view in record['views']:
        film_images.verify(studio, view['image_id'])
    return record

def listing(studio, project_id):
    film.project(studio, project_id)
    return {'references': list({r['id']: r for r in film._records(studio, PREFIX)
                           if r['project_id'] == project_id and studio.setting(PREFIX+r['id']) == r}.values())}

def save(studio, project_id, payload):
    film.project(studio, project_id)
    identity = payload.get('id') or 'reference.' + uuid4().hex
    film._id(identity, 'reference')
    with studio.lock, studio.db() as db:
        db.execute('BEGIN IMMEDIATE')
        prior = studio.setting(PREFIX + identity)
        if prior and prior['project_id'] != project_id:
            raise StudioError('Reference belongs to another project', 409)
        revision = prior['revision'] if prior else 0
        if type(payload.get('expected_revision')) is not int or payload['expected_revision'] != revision:
            raise StudioError('Reference changed; reload before saving', 409)
        if payload.get('kind') not in ('character', 'location', 'prop'):
            raise StudioError('Reference kind must be character, location or prop')
        views = payload.get('views')
        if not isinstance(views, list) or not 1 <= len(views) <= 32:
            raise StudioError('Use one to 32 named reference views')
        clean = []; seen = set()
        for view in views:
            if not isinstance(view, dict): raise StudioError('Invalid reference view')
            name = text(view.get('name'), 'View name', 100)
            if name in seen: raise StudioError('View names must be unique')
            seen.add(name)
            image = film_images.verify(studio, view.get('image_id'))
            clean.append({'name': name, 'image_id': image['id'], 'png_sha256': image['png']['sha256'],
                          'description': text(view.get('description', ''), 'View description', 1000, False)})
        record = {'id': identity, 'project_id': project_id, 'revision': revision+1,
                  'kind': payload['kind'], 'label': text(payload.get('label'), 'Reference label', 200),
                  'guidelines': text(payload.get('guidelines'), 'Visual guidelines', 2000),
                  'views': clean, 'created': prior['created'] if prior else utc_now(), 'updated': utc_now(),
                  'status': 'authored_reference_not_output_approval'}
        studio.store.save_snapshot(record)
        film._write(db, PREFIX+identity, record)
        film._write(db, PREFIX+identity+'.revision.'+str(record['revision']), record)
    return record

def resolve(studio, project_id, bindings):
    if not isinstance(bindings, list) or len(bindings) > 16:
        raise StudioError('Use at most 16 production reference bindings')
    clean = []; seen = set()
    for binding in bindings:
        if not isinstance(binding, dict) or type(binding.get('revision')) is not int or binding['revision'] < 1:
            raise StudioError('Pin a positive reference revision')
        record = get(studio, project_id, binding.get('id'), binding['revision'])
        key = (record['id'], record['revision'], binding.get('view'))
        if key in seen: raise StudioError('Duplicate reference binding')
        seen.add(key)
        view = next((v for v in record['views'] if v['name'] == binding.get('view')), None)
        if view is None: raise StudioError('Choose a named view from this reference revision')
        clean.append({'id': record['id'], 'revision': record['revision'], 'view': view['name'],
                      'record': record, 'selected_image_id': view['image_id']})
    return clean

def compile_shot(studio, project_id, payload):
    """Explicit preparation only: no job submission, approval, or timeline mutation."""
    bindings = resolve(studio, project_id, payload.get('bindings'))
    action = text(payload.get('action'), 'Shot action and camera direction', 2000)
    mode = payload.get('conditioning_mode', 'first_frame')
    if mode not in ('first_frame', 'reference_images'):
        raise StudioError('Choose first_frame or reference_images conditioning')
    result = {'production_reference_bindings': [
        {'id': b['id'], 'revision': b['revision'], 'view': b['view']} for b in bindings],
        'evidence': bindings, 'last_frame_id': None,
        'limitations': ['No guaranteed identity, object permanence, camera calibration, depth or shared 3D geometry. Review each generated take.']}
    if mode == 'reference_images':
        refs = []
        for b in bindings:
            record = b['record']
            view = next(v for v in record['views'] if v['name'] == b['view'])
            role = record['kind'] + ' ' + record['label'] + ', view ' + b['view']
            if view['description']: role += ': ' + view['description']
            refs.append({'image_id': b['selected_image_id'], 'role': role})
        refs = film_images.reference_parameters(refs)
        brief = action + '\n\nVisual continuity guidelines:\n' + '\n'.join(
            '<Picture ' + str(i+1) + '> is ' + ref['role'] + '. ' + bindings[i]['record']['guidelines']
            for i, ref in enumerate(refs))
        result.update(recipe_id=recipe.R2V_RECIPE_ID, reference_images=refs, first_frame_id=None,
                      conditioning={'mode': mode, 'additional_image_conditioning': True,
                                    'reference_images': refs, 'role_encoding': 'ordered Picture tokens in prompt'})
        result['limitations'].append('Experimental reference-to-video node with installed FL2VA weights; native REF2VA weights are not installed. Multi-reference consistency is not yet validated.')
    else:
        chosen = payload.get('conditioning_binding')
        if isinstance(chosen, dict):
            selected = next((b for b in bindings if all(b[k] == chosen.get(k) for k in ('id','revision','view'))), None)
        else:
            matches = [b for b in bindings if b['id'] == payload.get('conditioning_reference_id')]
            selected = matches[0] if len(matches) == 1 else None
        if selected is None: raise StudioError('Choose which specific reference view supplies the actual first frame')
        brief = action + '\n\nVisual continuity guidelines:\n' + '\n'.join(
            b['record']['label'] + ': ' + b['record']['guidelines'] for b in bindings)
        result.update(recipe_id=recipe.RECIPE_ID, reference_images=[], first_frame_id=selected['selected_image_id'],
                      conditioning={'mode': mode, 'first_frame': selected['selected_image_id'], 'additional_image_conditioning': False})
        result['limitations'].append('Only the selected first-frame view is supplied as an image. Other references contribute text guidelines.')
    text(brief, 'Compiled generation brief', 4000)
    result['brief'] = brief
    return result
