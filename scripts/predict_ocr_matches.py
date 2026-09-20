"""Run the API algorithm's matching stage in its own Python environment."""
from __future__ import annotations

import argparse
import contextlib
import json
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--object-root', type=Path, required=True)
    parser.add_argument('--inputs', type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.object_root / 'Object_detection_algorithm'))
    # Pipeline diagnostics must not corrupt the JSON result on stdout.
    with contextlib.redirect_stdout(sys.stderr):
        import cv2
        from run_pipeline import obtain_matches, PipelineConfig
        from src.template_image_class import TemplateImage
        from src.point_matching.Cluster_class import load_clusters

        template = TemplateImage.from_folder(str(args.inputs / 'template'), scale=1.0)
        scene = cv2.imread(str(args.inputs / 'scene.png'))
        if scene is None:
            raise ValueError('Cannot decode scene image')
        result = obtain_matches(
            scene, template,
            template_clusters_all=load_clusters(args.inputs / 'template/ocr_character_overlay.json'),
            scene_clusters=load_clusters(args.inputs / 'scene_ocr.json'),
            config=PipelineConfig(), debug=False,
        )
    print(json.dumps({'matches': result.api_matches()}, allow_nan=False))


if __name__ == '__main__':
    main()
