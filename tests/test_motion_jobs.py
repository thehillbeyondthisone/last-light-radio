import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageChops

from last_light_radio.comfy import ComfyError
from last_light_radio.generation import latest_event, load_request
from last_light_radio.live import LiveComfyClient
from last_light_radio.motion_jobs import (composite_actor_frame, poll_motion_generation,
                                          prepare_motion_inputs, production_graph,
                                          start_motion_generation)
from last_light_radio.store import ProjectStore, StoreError, sha256
from last_light_radio.video_tools import ffmpeg_path, sample_video, verify_video

ROOT = Path(__file__).resolve().parents[1]


def png(image):
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def definitions(graph):
    """Small independent worker-schema fixture, without models or a GPU."""
    result = {}
    for node in graph.values():
        inputs = {}
        for name, value in node["inputs"].items():
            if isinstance(value, list):
                kind = "*"
            else:
                kind = {str: "STRING", int: "INT", float: "FLOAT", bool: "BOOLEAN"}[type(value)]
            inputs[name] = [kind]
        result[node["class_type"]] = {"input": {"required": inputs}, "output": ["*", "*"], "output_node": node["class_type"] == "SaveImage"}
    return result


class MotionClient:
    base_url = "http://worker.invalid:8188"

    def __init__(self):
        self.graph = None
        self.uploads = []
        self.submissions = 0
        self.polls = 0
        self.downloads = 0
        self.fail_at = None
        self.ambiguous = False
        self.failure = False
        self.output_override = None
        self.definitions = definitions(production_graph())

    def probe(self):
        return {"connected": True, "object_info": copy.deepcopy(self.definitions), "system_stats": {"devices": []}, "errors": []}

    def upload_image(self, data, filename, subfolder):
        self.uploads.append((filename, data))
        return {"name": filename, "subfolder": subfolder, "type": "input", "path": subfolder + "/" + filename}

    def submit(self, graph, **kwargs):
        self.submissions += 1
        self.graph = copy.deepcopy(graph)
        if self.ambiguous:
            raise ComfyError("SUBMISSION_AMBIGUOUS", "Response lost")
        return {"prompt_id": "owned-production-prompt", "number": 1}

    def poll(self, prompt_id):
        self.polls += 1
        if self.failure:
            return {"status": "failed", "error": {"code": "WORKER_EXECUTION_FAILED"}}
        folder, stem = self.graph["14"]["inputs"]["filename_prefix"].rsplit("/", 1)
        images = [{"filename": f"{stem}_{i + 1:05d}_.png", "subfolder": folder.replace("/", "\\"), "type": "output"}
                  for i in range(self.graph["7"]["inputs"]["length"])]
        return {"status": "success", "prompt_id": prompt_id,
                "history": {"prompt": [1, prompt_id, copy.deepcopy(self.graph)], "status": {"messages": []}},
                "outputs": self.output_override or {"14": {"images": images}}}

    def download_png_output(self, reference):
        self.downloads += 1
        if self.fail_at == self.downloads:
            raise ComfyError("WORKER_OFFLINE", "Temporary disconnect")
        return png(Image.new("RGB", (768, 768), (140, 100, 60)))

    def system_stats(self):
        return {"devices": []}


def encode_fixture(store, relative, images, size, fps):
    """Exercise every assembled image/sample without an FFmpeg dependency."""
    for image in images:
        if image.mode != "RGB" or image.size != size:
            raise AssertionError("Encoder received wrong image geometry")
    data = b"\0\0\0\x18ftypisom-test-output"
    store.write_once(relative, data)
    return {"path": relative, "sha256": sha256(data), "bytes": len(data)}


class MotionJobTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "tests")
        self.addCleanup(self.temp.cleanup)
        self.store = ProjectStore(self.temp.name)
        self.client = MotionClient()
        self.local_id = "c" * 32
        self.first = Image.new("RGB", (800, 800), (10, 20, 30))
        self.last = self.first.copy()
        self.last.putpixel((150, 150), (40, 50, 60))
        self.background = Image.new("RGB", (800, 800), (11, 22, 33))
        self.mask = Image.new("L", (800, 800), 0)
        self.mask.paste(255, (100, 100, 200, 200))
        self.mask.putpixel((99, 100), 128)
        self.mask.putpixel((0, 0), 255)  # Outside the crop: must be clipped.
        def asset(name, image):
            data = png(image)
            path = f"masters/{name}.png"
            self.store.write_once(path, data)
            return {"id": "asset." + name, "path": path, "sha256": sha256(data)}
        self.profile = {"id": "reader-idle", "name": "Reader idle", "scene_id": "scene", "actor": "reader", "role": "idle",
                        "start_state": "reading", "end_state": "looking", "first": asset("first", self.first),
                        "last": asset("last", self.last), "background": asset("background", self.background), "mask": asset("mask", self.mask),
                        "crop": {"x": 16, "y": 16, "width": 768, "height": 768}, "frames": 3, "fps": 24,
                        "seed": 8, "prompt": "One breath", "reference_candidate_id": "legacy.1"}
        self.addCleanup(patch.stopall)
        patch("last_light_radio.motion_jobs.ffmpeg_path", return_value="fixture-ffmpeg").start()
        patch("last_light_radio.motion_jobs._encode_mp4", side_effect=encode_fixture).start()

    def start(self):
        return start_motion_generation(self.store, self.client, self.profile, "One restrained breath.", 8, local_job_id=self.local_id)

    def test_exact_separate_crops_protected_pixels_and_unapproved_provenance(self):
        template = production_graph()
        sources = {key: self.store.resolve(self.profile[key]["path"]).read_bytes() for key in ("first", "last", "mask", "background")}
        self.start()
        request = load_request(self.store, self.local_id)
        self.assertEqual(request["pipeline"], "actor_motion_v1")
        self.assertEqual(len(self.client.uploads), 2)
        self.assertNotEqual(self.client.uploads[0][1], self.client.uploads[1][1])
        for name, full in (("first", self.first), ("last", self.last)):
            with Image.open(self.store.resolve(request["prepared_inputs"][name]["path"])) as crop:
                self.assertIsNone(ImageChops.difference(crop, full.crop((16, 16, 784, 784))).getbbox())
        result = poll_motion_generation(self.store, self.client, self.local_id)
        candidate = result["candidate"]
        self.assertEqual(candidate["review_status"], "candidate")
        self.assertFalse(candidate["canon_approved"])
        self.assertTrue(candidate["history_workflow_verified"])
        self.assertEqual(candidate["motion"]["reference_candidate_id"], "legacy.1")
        with Image.open(self.store.resolve(candidate["motion"]["lossless_samples"]["middle"]["path"])) as assembled:
            self.assertEqual(assembled.getpixel((0, 0)), self.background.getpixel((0, 0)))
            self.assertEqual(assembled.getpixel((300, 300)), self.background.getpixel((300, 300)))
            self.assertEqual(assembled.getpixel((150, 150)), (140, 100, 60))
            self.assertEqual(assembled.getpixel((99, 100)), (76, 61, 47))
        self.assertEqual(production_graph(), template)
        for key, data in sources.items():
            self.assertEqual(self.store.resolve(self.profile[key]["path"]).read_bytes(), data)
        reopen = ProjectStore(self.temp.name)
        self.assertEqual(poll_motion_generation(reopen, self.client, self.local_id)["candidate"], candidate)
        self.assertEqual((self.client.submissions, self.client.polls, self.client.downloads), (1, 1, 3))
        with self.assertRaises(ComfyError) as error:
            self.start()
        self.assertEqual(error.exception.code, "JOB_EXISTS")
        self.assertEqual(self.client.submissions, 1)

    def test_missing_original_vae_fails_before_upload_but_explicit_variant_is_recorded(self):
        self.client.definitions["VAELoader"]["input"]["required"]["vae_name"] = [["installed-int8.safetensors"]]
        with self.assertRaises(ComfyError) as error:
            self.start()
        self.assertEqual(error.exception.code, "MISSING_MODEL")
        self.assertEqual((len(self.client.uploads), self.client.submissions), (0, 0))
        self.profile["vae_name"] = "installed-int8.safetensors"
        self.start()
        request = load_request(self.store, self.local_id)
        self.assertEqual(self.client.graph["3"]["inputs"]["vae_name"], "installed-int8.safetensors")
        self.assertFalse(request["execution_variant"]["exact_recovered_model_recipe"])
        self.assertEqual(production_graph()["3"]["inputs"]["vae_name"], "minimax_h3_video_vae_fp16.safetensors")

    def test_download_restart_uses_saved_verified_frames_and_never_resubmits(self):
        self.start()
        self.client.fail_at = 2
        with self.assertRaises(ComfyError):
            poll_motion_generation(self.store, self.client, self.local_id)
        self.assertEqual(latest_event(self.store, self.local_id)["status"], "download_failed")
        candidate = poll_motion_generation(ProjectStore(self.temp.name), self.client, self.local_id)["candidate"]
        self.assertEqual(len(candidate["motion"]["raw_frames"]), 3)
        self.assertEqual(self.client.downloads, 4)  # Successful first frame reused.
        self.assertEqual(self.client.submissions, 1)
        self.store.resolve(candidate["motion"]["raw_frames"][0]["path"]).write_bytes(b"changed")
        with self.assertRaises(ComfyError) as error:
            poll_motion_generation(self.store, self.client, self.local_id)
        self.assertEqual(error.exception.code, "CANDIDATE_CHECKSUM_MISMATCH")

    def test_foreign_duplicate_missing_or_wrong_dimension_outputs_are_refused(self):
        self.start()
        expected = self.client.poll("owned-production-prompt")["outputs"]
        cases = []
        foreign = copy.deepcopy(expected)
        foreign["14"]["images"][0]["subfolder"] = "another-job"
        cases.append(foreign)
        duplicate = copy.deepcopy(expected)
        duplicate["14"]["images"][1] = duplicate["14"]["images"][0]
        cases.append(duplicate)
        missing = copy.deepcopy(expected)
        missing["14"]["images"].pop()
        cases.append(missing)
        for value in cases:
            self.client.output_override = value
            with self.assertRaises(ComfyError):
                poll_motion_generation(self.store, self.client, self.local_id)
        self.assertEqual(self.client.downloads, 0)
        self.client.output_override = None
        self.client.download_png_output = lambda _: png(Image.new("RGB", (32, 32)))
        with self.assertRaises(ComfyError) as error:
            poll_motion_generation(self.store, self.client, self.local_id)
        self.assertEqual(error.exception.code, "MOTION_FRAME_GEOMETRY")

    def test_modified_sources_and_executed_workflow_are_refused(self):
        self.start()
        original = self.store.resolve(self.profile["last"]["path"]).read_bytes()
        self.store.resolve(self.profile["last"]["path"]).write_bytes(b"changed")
        with self.assertRaises(StoreError):
            poll_motion_generation(self.store, self.client, self.local_id)
        self.store.resolve(self.profile["last"]["path"]).write_bytes(original)
        self.client.graph["11"]["inputs"]["noise_seed"] += 1
        with self.assertRaises(ComfyError) as error:
            poll_motion_generation(self.store, self.client, self.local_id)
        self.assertEqual(error.exception.code, "HISTORY_WORKFLOW_MISMATCH")
        self.assertEqual(self.client.downloads, 0)

    def test_ambiguous_submission_is_durable_and_never_retried(self):
        self.client.ambiguous = True
        with self.assertRaises(ComfyError):
            self.start()
        self.assertEqual(load_request(self.store, self.local_id)["local_job_id"], self.local_id)
        with self.assertRaises(ComfyError) as error:
            poll_motion_generation(self.store, self.client, self.local_id)
        self.assertEqual(error.exception.code, "SUBMISSION_UNRESOLVED")
        self.assertEqual(self.client.submissions, 1)

    def test_failed_worker_remains_failure_without_media_or_retry(self):
        self.start()
        self.client.failure = True
        result = poll_motion_generation(self.store, self.client, self.local_id)
        self.assertEqual(result["status"], "failed")
        self.assertNotIn("candidate", result)
        self.assertEqual(self.client.downloads, 0)
        self.assertEqual(self.client.submissions, 1)

    def test_pure_compositor_retains_generated_endpoints_without_fading(self):
        inputs = prepare_motion_inputs(self.store, self.profile)
        generated = Image.new("RGB", (768, 768), (100, 110, 120))
        for index in (0, 2):
            image = composite_actor_frame(inputs["background"], inputs["last"], generated, inputs["mask"], self.profile["crop"], index, 3, inputs["policy"])
            self.assertEqual(image.getpixel((150, 150)), (100, 110, 120))
            self.assertEqual(image.getpixel((0, 0)), (11, 22, 33))


class PngTransportTests(unittest.TestCase):
    def test_png_download_checks_type_signature_and_reference(self):
        data = png(Image.new("RGB", (2, 2)))
        responses = [(200, {"content-type": "image/png"}, data),
                     (200, {"content-type": "image/webp"}, data),
                     (200, {"content-type": "image/png"}, b"not-png")]
        client = LiveComfyClient("http://worker.invalid", transport=lambda *args: responses.pop(0))
        reference = {"filename": "frame_00001_.png", "subfolder": "job", "type": "output"}
        self.assertEqual(client.download_png_output(reference), data)
        for _ in range(2):
            with self.assertRaises(ComfyError):
                client.download_png_output(reference)
        for bad in ({**reference, "type": "input"}, {**reference, "subfolder": "../job"}, {**reference, "filename": "x.webp"}):
            with self.assertRaises(ComfyError):
                client.download_png_output(bad)

    def test_optional_cpu_encoder_produces_playable_mp4(self):
        try:
            ffmpeg_path()
        except ComfyError:
            self.skipTest("Optional FFmpeg media dependency is not installed")
        from last_light_radio.motion_jobs import _encode_mp4
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as directory:
            store = ProjectStore(directory)
            images = [Image.new("RGB", (32, 24), (20 + index * 15, 80, 100)) for index in range(4)]
            output = _encode_mp4(store, "candidates/test.mp4", iter(images), (32, 24), 24)
            # A crash after encoding but before candidate publication must be
            # resumable through the store's non-overwriting write contract.
            repeated = _encode_mp4(store, "candidates/test.mp4", iter(images), (32, 24), 24)
            self.assertEqual(repeated, output)
            verify_video(store.resolve(output["path"]))
            self.assertEqual(sha256(store.resolve(output["path"]).read_bytes()), output["sha256"])
            with Image.open(io.BytesIO(sample_video(store.resolve(output["path"]), 0))) as decoded:
                self.assertEqual(decoded.size, (32, 24))


if __name__ == "__main__":
    unittest.main()
