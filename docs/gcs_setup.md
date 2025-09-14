Google Cloud Storage for API Builder
====================================

This app now stores API builder data (image + doc.json) in a GCS bucket.

- Default bucket: `api_information_storage` (override with env `API_STORAGE_BUCKET`).
- Service account key: `secrets/api_bucket_db_key.json` (override with env `API_BUCKET_KEY_FILE`).

Install dependency
------------------

Use the helper script to install dependencies locally:

```
./Install_additional_modules.sh
```

or install with pip:

```
pip install google-cloud-storage
```

How it works
------------

- On create: image is uploaded to `gs://<bucket>/<user_id>/<api_id>/image.<ext>` and a `doc.json` is saved in the same folder.
- On save: the `doc.json` is updated in the bucket.
- On list/load: the server lists `<user_id>/*/doc.json` and returns docs. Thumbnails/images are proxied via `/builder/images/{api_id}` so the bucket can remain private.

Notes
-----

- The user id used for folder names is the authenticated email (fallback to sub/name).
- You can keep the bucket private; the server reads with the service account and streams images to the browser.

