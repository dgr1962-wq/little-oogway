BEGIN;
DO $$
DECLARE
 p uuid; c uuid; r uuid; t uuid; m uuid; m2 uuid; s uuid;
BEGIN
 IF current_database() <> 'tokenspace_v2_dev' THEN RAISE EXCEPTION 'Wrong database'; END IF;
 IF current_setting('server_version_num')::integer / 10000 <> 16 THEN RAISE EXCEPTION 'Expected PostgreSQL 16'; END IF;
 IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname='vector') THEN RAISE EXCEPTION 'Missing pgvector'; END IF;
 INSERT INTO tokenspace_v2.participants(identity_key,name,kind,provider,model)
 VALUES ('model:smoke:smoke:smoke','smoke','model','ollama','qwen3:8b')
 RETURNING id INTO p;
 INSERT INTO tokenspace_v2.conversations(title,provenance)
 VALUES ('smoke','{"source":"rollback smoke test"}') RETURNING id INTO c;
 INSERT INTO tokenspace_v2.rounds(conversation_id,ordinal) VALUES(c,0) RETURNING id INTO r;
 INSERT INTO tokenspace_v2.turns(round_id,participant_id,ordinal,content)
 VALUES(r,p,0,'test response') RETURNING id INTO t;
 INSERT INTO tokenspace_v2.memory_sources(
  source_type,source_locator,content_sha256,metadata
 ) VALUES(
  'smoke','smoke/source.txt',repeat('0',64),'{"retrieval_only":true}'
 ) RETURNING id INTO s;
 INSERT INTO tokenspace_v2.memories(
  source_turn_id,source_id,source_ordinal,content
 ) VALUES(t,s,0,'test searchable memory') RETURNING id INTO m;
 INSERT INTO tokenspace_v2.memory_embeddings(
  memory_id,model,model_digest,dimensions,embedding
 ) VALUES(
  m,'smoke-model','smoke-digest',768,
  array_prepend(1::real,array_fill(0::real,ARRAY[767]))::vector
 );
 INSERT INTO tokenspace_v2.memories(source_turn_id,source_id,source_ordinal,content)
 VALUES(t,s,1,'test searchable memory') RETURNING id INTO m2;
 INSERT INTO tokenspace_v2.memory_relations(
  canonical_memory_id,related_memory_id,relation_type,confidence,review_status,evidence,
  preferred_memory_id,preference_reason
 ) VALUES(
  m,m2,'exact_duplicate',1,'confirmed','{"method":"exact-content"}',
  m,'smoke preference'
 );
 IF NOT EXISTS (
 SELECT 1 FROM tokenspace_v2.memories mm
 JOIN tokenspace_v2.turns tt ON tt.id=mm.source_turn_id
 JOIN tokenspace_v2.rounds rr ON rr.id=tt.round_id
 JOIN tokenspace_v2.conversations cc ON cc.id=rr.conversation_id
 JOIN tokenspace_v2.participants pp ON pp.id=tt.participant_id
 WHERE mm.id=m AND mm.content='test searchable memory' AND tt.content='test response'
 AND cc.id=c AND pp.id=p
 ) THEN RAISE EXCEPTION 'Readback failed'; END IF;
 IF NOT EXISTS (
  SELECT 1 FROM tokenspace_v2.memories
  WHERE id=m AND search_vector @@ plainto_tsquery('english','searchable')
 ) THEN RAISE EXCEPTION 'Full-text search failed'; END IF;
 IF NOT EXISTS (
  SELECT 1 FROM tokenspace_v2.memory_embeddings
  WHERE memory_id=m AND vector_dims(embedding)=768
 ) THEN RAISE EXCEPTION 'Embedding storage failed'; END IF;
 IF NOT EXISTS (
  SELECT 1 FROM tokenspace_v2.memory_relations
  WHERE canonical_memory_id=m AND related_memory_id=m2
    AND relation_type='exact_duplicate' AND review_status='confirmed'
    AND preferred_memory_id=m AND preference_reason='smoke preference'
 ) THEN RAISE EXCEPTION 'Memory relation storage failed'; END IF;
 BEGIN
 INSERT INTO tokenspace_v2.turns(round_id,participant_id,ordinal,content) VALUES(r,p,0,'duplicate');
 RAISE EXCEPTION 'Duplicate order accepted';
 EXCEPTION WHEN unique_violation THEN NULL;
 END;
 BEGIN
 INSERT INTO tokenspace_v2.rounds(conversation_id,ordinal) VALUES(gen_random_uuid(),1);
 RAISE EXCEPTION 'Missing conversation accepted';
 EXCEPTION WHEN foreign_key_violation THEN NULL;
 END;
 BEGIN
 INSERT INTO tokenspace_v2.memories(content) VALUES(' ');
 RAISE EXCEPTION 'Empty memory accepted';
 EXCEPTION WHEN check_violation THEN NULL;
 END;
 RAISE NOTICE 'PASS: conversation, provenance, retrieval, consolidation, and constraint checks';
END $$;
ROLLBACK;
