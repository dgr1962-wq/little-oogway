# Nomic Atlas export

`export_public_atlas.py` reads TokenSpace in read-only mode and accepts only
active `https://anykeycafe.com/` or `https://www.anykeycafe.com/` absorbed URL
sources. It replaces memory UUIDs with stable one-way identifiers. Local files,
conversations, private memories, and the legacy database are excluded.

The generated JSONL can be large and is deliberately ignored by Git. Keep the
Nomic token in the ignored `.nomic-token` file with mode `600`, or adapt the
uploader to another local secret provider. Review `manifest.json` and the
dataset before any upload.

The first published map is:

https://atlas.nomic.ai/data/dgr1962/little-oogway-public-anykeycafe-memory-field/map
