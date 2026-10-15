# Qwen and Ollama compatibility note

Production uses Ollama `qwen3:8b`, an 8.2B Q4_K_M GGUF artifact with manifest
SHA-256 `500a1f067a9f782620b40bee6f7b0c89e17ae61f686b92c24933e4ca4b2b8b41`.
The training reference is `Qwen/Qwen3-8B` at immutable revision
`b968826d9c46dd6066d109eabc6255188de91218`.

The local Ollama manifest identifies the architecture, quantization, and model
layer but does not prove byte-for-byte ancestry from that Hugging Face commit.
Consequently, future adapter compatibility must be demonstrated rather than
assumed.

A PEFT adapter is not directly loadable by Ollama. A future reviewed path would
need to:

1. Verify the adapter's exact upstream base revision and tokenizer.
2. Load and evaluate the adapter with Transformers/PEFT.
3. Optionally merge it into the matching full-precision base in a disposable
   workspace, preserving the unmerged adapter.
4. Convert the matched model or adapter with a version-pinned `llama.cpp`
   conversion tool supported by the target Ollama/llama.cpp release.
5. Quantize to a new, separately named GGUF artifact.
6. Compare it with the unmodified baseline before any promotion.

This preparation pass performs none of those production conversion steps and
does not modify the existing Ollama manifest or blobs.
