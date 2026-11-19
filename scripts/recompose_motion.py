"""Recompose saved actor PNGs through a compatible mask revision, without a GPU."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from last_light_radio.recompose import recompose
from last_light_radio.studio import Studio


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--recipe-id", required=True)
    parser.add_argument("--store", default=".local/studio")
    args = parser.parse_args()
    candidate = recompose(Studio(args.store), args.source_id, args.recipe_id)
    print(json.dumps({"id": candidate["id"], "status": candidate["status"], "media": candidate["metadata"]["outputs"][0]["path"]}))


if __name__ == "__main__":
    main()
