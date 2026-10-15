# Private SearXNG research service

This Compose service gives the authenticated Little Oogway Core session a
zero-fee metasearch endpoint. It binds only to `127.0.0.1:8888`; it is not a
public search instance and is not connected to the WordPress assistant or the
Roundtable bridge.

Create a local ignored `.env` containing a long random `SEARXNG_SECRET`, then:

```bash
docker compose up -d
curl -X POST http://127.0.0.1:8888/search \
  -d 'q=SearXNG&format=json&categories=general'
```

The private Core adapter permits bounded search and one-page HTTPS reading. It
blocks local/private network targets, credentials in URLs, nonstandard ports,
large responses, executable content, and automatic ingestion. Returned text is
explicitly labeled as untrusted evidence and must be verified before use.
