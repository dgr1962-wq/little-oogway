# Atlas snapshot boundary

The existing public Atlas exporter and published dataset remain unchanged.
They accept only active public AnyKeyCafe URL sources and exclude conversations,
local files, private memories, and legacy data.

`scripts/atlas_snapshot.py` adds a private, upload-free snapshot interface for:

- approved memory embeddings, labelled `stored_knowledge`; and
- experimental response embeddings, labelled `model_behavior_observation`.

These labels prevent a visualization change caused by stored information from
being described as a change in the model itself. Snapshots are immutable,
versioned directories with data hashes. The tool refuses unapproved memory
rows and never invokes Nomic or replaces an existing snapshot.
