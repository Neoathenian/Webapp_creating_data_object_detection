# Matches annotation page

Open `/matches/` or select **Matches** in the header. Choose CI or Talon and an
OCR scene from the thumbnail sidebar. The page shares the builder’s layout,
font, toolbar, and button styles. Click a point in either image, then its counterpart on the other side
to confirm a pair. Selecting a point hides incompatible points on the opposite
image. Press Escape or Clear selection to restore all points.

Compatibility means the exact same nonempty OCR character (case sensitive),
with each point used at most once. There is no automatic geometric pruning.
Points without unused counterparts, unrecognized points, and confirmed points
show a small × and cannot be selected. Confirmed pairs have colored connecting
lines; expand **Confirmed matches** in the sidebar and remove them there to make their points available again.
Click a row in **Predictions** or **Confirmed matches** to focus that pair and
inspect it individually on the board. Click the same row again, press Escape,
or use Clear selection to restore the full view.
Matched points (×) on the board are also clickable: selecting one jumps to and
highlights its row in **Confirmed matches**, and the board isolates that pair.
When a prediction row is focused, press Enter to accept it and move to the next
prediction. Press Backspace or Delete to dismiss it and move to the next one.
Prediction navigation order is stabilized by a reading-order sort that groups
nearby y-values into text lines and large x-gaps into word-like chunks, using
both template and scene point coordinates to reduce row-to-row oscillation.
Enable **Hide current matches** in the toolbar to temporarily hide confirmed-match
points, their labels, and their connecting lines while you inspect remaining
unmatched characters.
Scroll to zoom, drag the background to pan, and use Fit to reset the view.
Undo/redo operates on the current sample. **Save matches** (Ctrl/Cmd+S) persists
changes; **Export** downloads the current pairs with their OCR point coordinates,
including any unsaved changes. Switching samples or leaving the page warns about
unsaved changes.

## Files

Templates are read directly from `webapp_storage_outputs/local/templates/`.
Scenes and annotations live in `webapp_storage_outputs/local/matches/`:

```text
local/
├── templates/
│   ├── CI/{image.png,ocr_character_overlay.json,bboxes.json}
│   └── Talon/{image.png,ocr_character_overlay.json,bboxes.json}
└── matches/
    ├── CI/<sample>/
    │   ├── ocr_character_overlay.json
    │   ├── input_image.png
    │   ├── rotated_image.png
    │   └── manual_matches.json
    └── Talon/<sample>/...
```

`manual_matches.json` is created on save. It contains a versioned list of
`{template_id, scene_id}` pairs, coordinate spaces, source fingerprints, a revision,
and an update timestamp. IDs are zero-based positions in the original OCR
`detections` array. The API response and exported JSON also supply `cluster_index`
for the API algorithm's list, which excludes detections without labels.
Original OCR files and images are never rewritten by annotation saves.

Point positions use polygon centroids, following
`Object_detection_algorithm/src/point_matching/Cluster_class.py`. Images use
`metadata.coordinates`: for `rotated_image`, the embedded rotated image is used
(or `rotated_image.png` if the embedded image is absent). Using `input_image.png`
for those coordinates would misalign the points.

Template points inside `extract_text` or `noise` bounding boxes are excluded,
following the API's `TemplateImage.keep_mask` and `Cluster.is_in_mask`. Reference
boxes are not exclusions. The mask uses the API's axis-aligned boxes, separator
splitting, integer truncation, and rounded-centroid lookup. Excluded points are
not displayed or accepted when saving pairs. Scene points are not masked.
Filtering preserves original detection IDs and `cluster_index`; template points
also expose `matching_cluster_index` for the filtered, labeled cluster list.
The current mask is read on each load/save and included in the fingerprint.
The old `matches/_templates` snapshots are no longer used.

Saves validate point IDs, matching characters, and uniqueness on both sides.
Files are replaced atomically. Revision checks reject stale browser saves, and
source fingerprints reject annotations whose OCR/image inputs or template mask have changed.
This is a shared local workspace, following the webapp's local storage layout.
Run it with one application worker; the save lock is process-local.

## Verification

Run `PythonPortable/env/bin/python -m unittest discover -s tests -v`.
The tests cover image coordinate selection, API-compatible centroids, persistence,
invalid and duplicate matches, stale saves, changed OCR data, authentication,
path validation, and catalog filtering.
