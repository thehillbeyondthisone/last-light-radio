"""Semantically reconstructed proven H3 text-to-joint-AV recipe.

Source raw-byte hash identifies the inspected Harbinger workflow. The adapter
has its own canonical graph hash: this is NOT claimed to be a byte-for-byte copy.
No reference conditioning was used in the successful source test.
"""
import copy
import json
from .comfy import workflow_sha256

SOURCE_RAW_SHA256 = '864d37420dc4c55902ffb59ef688c88e5c396b9edb55e60e9b2ceefd2050f1c1'
SOURCE_PROMPT_ID = 'c2e7ce24-2b9a-406c-bbe2-de0ba1f8d179'
GRAPH = json.loads(r'''{"2":{"class_type":"UNETLoader","inputs":{"unet_name":"minimax_h3_fl2va_pruned_int8_convrot.safetensors","weight_dtype":"default"}},"3":{"class_type":"CLIPLoader","inputs":{"clip_name":"qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors","type":"minimax","device":"default"}},"4":{"class_type":"VAELoader","inputs":{"vae_name":"minimax_h3_video_vae_int8_convrot.safetensors"}},"5":{"class_type":"LoraLoaderModelOnly","inputs":{"model":["2",0],"lora_name":"minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors","strength_model":1.0}},"6":{"class_type":"MiniMaxH3ImageToVideo","inputs":{"clip":["3",0],"vae":["4",0],"prompt":"A cinematic close-up of a small brass desk bell on a dark wooden table in a quiet warmly lit workshop. A gloved hand enters from the right, presses the bell once in the middle of the shot, then withdraws. The bell rings with one clear bright metallic ding that gently decays. Quiet natural room ambience throughout. Locked camera, shallow depth of field, realistic brass reflections, no music, no speech, no text. One continuous five-second shot. Sound must match the visible bell press.","width":672,"height":384,"length":124}},"7":{"class_type":"BasicGuider","inputs":{"model":["5",0],"conditioning":["6",0]}},"8":{"class_type":"RandomNoise","inputs":{"noise_seed":2026111301}},"9":{"class_type":"KSamplerSelect","inputs":{"sampler_name":"res_multistep"}},"10":{"class_type":"BasicScheduler","inputs":{"model":["5",0],"scheduler":"simple","steps":8,"denoise":1.0}},"11":{"class_type":"SamplerCustomAdvanced","inputs":{"noise":["8",0],"guider":["7",0],"sampler":["9",0],"sigmas":["10",0],"latent_image":["6",1]}},"12":{"class_type":"VAEDecode","inputs":{"samples":["15",0],"vae":["4",0]}},"13":{"class_type":"CreateVideo","inputs":{"images":["12",0],"fps":24.0,"bit_depth":8,"color_space":"sRGB","codec":"none","audio":["17",0]}},"14":{"class_type":"SaveVideo","inputs":{"video":["13",0],"filename_prefix":"film-pipeline-av-test-20261113/bell-av","format":"mp4","format.codec":"h264","format.codec.encoding":"re-encode","format.codec.encoding.crf":20.0}},"15":{"class_type":"LTXVSeparateAVLatent","inputs":{"av_latent":["11",0]}},"16":{"class_type":"VAELoader","inputs":{"vae_name":"minimax_h3_audio_vae_fp32.safetensors"}},"17":{"class_type":"VAEDecodeAudio","inputs":{"vae":["16",0],"samples":["15",1]}}}''')
GRAPH_SHA256 = workflow_sha256(GRAPH)
RECIPE_ID = 'h3_joint_av.' + GRAPH_SHA256
PIPELINE = 'h3_joint_av_v1'
# Take length (2026-11-19). Only 124 frames is proven end to end; others are accepted by the graph but untested.
DEFAULT_FRAMES = 124
MIN_FRAMES = 48
MAX_FRAMES = 240  # hard ceiling; the creator's coherence limit (default 124) is set in the Generate tab
FRAME_STEP = 4


def frames(value=None):
    if value is None:
        return DEFAULT_FRAMES
    if type(value) is not int or not MIN_FRAMES <= value <= MAX_FRAMES or value % FRAME_STEP:
        raise ValueError(f'Clip length must be {MIN_FRAMES}-{MAX_FRAMES} frames in steps of {FRAME_STEP}')
    return value
BINDINGS = {'brief': ['6','prompt'], 'seed': ['8','noise_seed'], 'filename_prefix': ['14','filename_prefix'],
            'output': {'node_id': '14', 'key': 'images', 'media': 'muxed_mp4'}}

# Experimental adapter: the observed lighthouse run reused FL2VA weights.
# Native REF2VA weights were not installed; multi-image quality is unverified.
R2V_GRAPH = copy.deepcopy(GRAPH)
R2V_GRAPH['6']['class_type'] = 'MiniMaxH3ReferenceToVideo'
R2V_GRAPH['6']['inputs']['ref_image_size'] = 'match'
R2V_GRAPH_SHA256 = workflow_sha256(R2V_GRAPH)
R2V_RECIPE_ID = 'h3_reference_av.experimental_fl2va.' + R2V_GRAPH_SHA256
R2V_SOURCE_PROMPT_ID = 'd90f832f-664c-4a6d-9079-f553ca37cd94'


def public_recipe(recipe_id=None):
    if recipe_id == R2V_RECIPE_ID:
        recipe = public_recipe()
        recipe.update({
            'id': R2V_RECIPE_ID,
            'name': 'H3 reference images + sound (experimental FL2VA)',
            'mode': 'reference_images_to_av',
            'conditioning_mode': 'reference_images',
            'max_reference_images': 9,
            'min_reference_images': 1,
            'experimental': True,
            'first_frame_tested': False,
            'last_frame_tested': False,
            'multi_reference_tested': False,
            'single_reference_executed': True,
            'native_ref2va_weights_available': False,
            'workflow_sha256': R2V_GRAPH_SHA256,
            'source_prompt_id': R2V_SOURCE_PROMPT_ID,
            'recipe_origin': 'experimental adaptation of observed single-reference lighthouse execution',
            'reference_quality_note': (
                'Experimental: reuses FL2VA weights and FL2V Turbo8 LoRA, not specialized REF2VA weights. '
                'Only single-image execution has been observed; multi-image quality, identity and spatial '
                'consistency are unverified. Character/location roles are prompt instructions, not hard constraints.'),
        })
        for key in ('source_raw_sha256', 'first_frame_evidence_prompt_id', 'last_frame_evidence_prompt_id'):
            recipe.pop(key, None)
        return recipe
    if recipe_id not in (None, RECIPE_ID):
        raise ValueError('Unknown H3 recipe ID: ' + str(recipe_id))
    return {'id': RECIPE_ID, 'name': 'H3 joint video + sound (text or frame references)', 'pipeline': PIPELINE,
            'mode': 'text_or_reference_to_av', 'reference_supported': True,
            'conditioning_mode': 'first_last_frames', 'max_reference_images': 2,
            'first_frame_tested': True, 'last_frame_tested': True,
            'last_frame_evidence_prompt_id': '505689fe-86ea-45ef-a554-c95128589bb2',
            'reference_quality_note': 'First and last conditioning executed successfully; endpoint similarity is not a pixel-exact guarantee',
            'first_frame_evidence_prompt_id': '0b57f4b7-df82-4e9b-a247-a59c7a287e6e', 'width': 672, 'height': 384,
            'frames': DEFAULT_FRAMES, 'proven_frames': [DEFAULT_FRAMES], 'min_frames': MIN_FRAMES, 'max_frames': MAX_FRAMES, 'frame_step': FRAME_STEP, 'fps': 24, 'steps': 8, 'default_seed': 2026111301,
            'workflow_sha256': GRAPH_SHA256, 'source_raw_sha256': SOURCE_RAW_SHA256,
            'source_prompt_id': SOURCE_PROMPT_ID, 'recipe_origin': 'semantic reconstruction of inspected successful workflow',
            'requires_brief': True}

def public_recipes():
    return [public_recipe(), public_recipe(R2V_RECIPE_ID)]


def prepared(brief, seed, prefix, recipe_id=None, length=None):
    public_recipe(recipe_id)  # Reject unknown IDs rather than silently changing models.
    graph = copy.deepcopy(R2V_GRAPH if recipe_id == R2V_RECIPE_ID else GRAPH)
    graph['6']['inputs']['prompt'] = brief
    graph['6']['inputs']['length'] = frames(length)
    graph['8']['inputs']['noise_seed'] = seed
    graph['14']['inputs']['filename_prefix'] = prefix
    return graph
