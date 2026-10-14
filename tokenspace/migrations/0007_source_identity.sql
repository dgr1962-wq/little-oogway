ALTER TABLE tokenspace_v2.memory_sources
DROP CONSTRAINT memory_sources_content_sha256_key;

ALTER TABLE tokenspace_v2.memory_sources
ADD CONSTRAINT memory_sources_identity_unique
UNIQUE (source_type, source_locator, content_sha256);
