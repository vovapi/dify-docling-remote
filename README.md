# Docling Remote for Dify

A lightweight Dify plugin for a separately deployed **Docling Serve**. Document conversion, OCR, table extraction and chunking run on your server; the plugin installs no Docling, Torch or model weights.

[Русский](README.ru.md) · [Releases](https://github.com/vovapi/dify-docling-remote/releases) · [Privacy](PRIVACY.md)

## Installation

1. Deploy Docling Serve separately and provision its models and OCR languages. The tested baseline is **Serve 1.21.0**; see its [deployment instructions](https://github.com/docling-project/docling-serve) and the tested [server constraints](https://github.com/vovapi/dify-docling-remote/blob/v0.1.4/docs/serve-requirements.txt).
2. Download `docling-remote-0.1.4.difypkg` from [release v0.1.4](https://github.com/vovapi/dify-docling-remote/releases/tag/v0.1.4) and install it in Dify → Plugins → Install from local package. Follow your administrator's policy for private plugins.
3. Configure the provider's **Docling Serve URL**, such as `http://docling-serve:5001`, without `/v1`. Set the optional API key matching `DOCLING_SERVE_API_KEY` on Serve.
4. Run **Server health**, then add **Convert documents** to a workflow and bind uploaded files to its Documents input.

The plugin runtime uses Python 3.12. In Docker, `localhost` refers to the plugin container: connect Serve and the plugin daemon to a shared network, or use an appropriate host gateway. An optional [Compose example](https://github.com/vovapi/dify-docling-remote/blob/v0.1.4/compose.yaml) is provided but has not been integration-tested. Dify Cloud needs an explicitly configured network path to private servers. Use HTTPS across untrusted networks.

## Usage and limits

- Submit 1–10 files, each nonempty and at most 50 MiB. All inputs are downloaded before conversion starts to avoid expiry during long batches.
- Choose Markdown, Docling JSON, HTML, text or DocTags exports. Outputs are `text`, structured `json` and a ZIP under `files`.
- OCR languages, standard/VLM pipelines, enrichment and hierarchical/hybrid chunking depend on installed server models. Chunking reuses converted Docling JSON without repeating OCR.
- The default PDF backend is `pypdfium2`: Serve 1.21.0 / Jobkit 1.24.0 rejected the default `docling_parse` backend in testing. Select alternatives only with compatible server dependencies.
- Timeout is per document: 600 seconds by default, configurable from 10 to 7000. Allow sufficient Dify workflow time for the whole batch. A timeout does not cancel server work; requests are not retried automatically.
- Each JSON response and accumulated raw results are bounded to 100 MiB. Mixed batches retain per-document failures; all-failed batches raise an error. `partial_success` remains explicit and may require content review.

Full exports and embedded images stay in the ZIP. Inline JSON removes embedded images and is limited to 2 MiB using Unicode-escaped serialization. Large results retain per-file Markdown when it fits; otherwise `inline_text_omitted` marks omitted text and `full_result_in_zip` points to the archive. Combined text is limited to 256K characters with an explicit truncation notice. Downstream analysis must check these markers.

[examples/workflow_texts.py](https://github.com/vovapi/dify-docling-remote/blob/v0.1.4/examples/workflow_texts.py) provides a Dify Code node adapter: bind `docling_json` and `docling_text` to the tool outputs. It returns `texts` and `files_count`, accepts nonempty partial results and rejects failed documents or omitted text. If structured results are unavailable, it rejects truncated combined text.

## Compatibility

Previously verified with Dify 1.17.1, native Linux arm64 plugin runtime and Docling Serve 1.21.0: multilingual HTML, scanned PDFs, exports, hierarchical chunking and batch conversion. Conversion success does not guarantee accurate OCR. CUDA, VLM/enrichment inference, Dify Cloud, amd64 runtime and full-scale load have not been verified. Marketplace approval is not claimed.

## Development

```sh
uv sync --frozen
uv run pytest -q
uv run python scripts/package.py --cli /path/to/dify
```

Python 3.12 and the official Dify CLI are required. Packaging stages an explicit runtime allowlist and writes the package plus `SHA256SUMS` into ignored `dist/`. CI runs tests and checks that `requirements.txt` matches `uv.lock`; update dependencies together.

For an optional real-server smoke test, set `DOCLING_TEST_URL` and `DOCLING_TEST_API_KEY`, then run `uv run python -m scripts.integration`. An optional `DOCLING_TEST_SCAN` points to a local scan containing `12345`. Never commit keys, input documents, environments or model weights.

## Privacy and support

Documents and filenames go to the administrator-configured Serve instance. Workflow inputs cannot set the server URL. Redirects and environment proxies are disabled; TLS verification is enabled. Raw server error bodies and credentials are not exposed in client diagnostics. Dify and Serve retention policies remain the administrator's responsibility. See [PRIVACY.md](PRIVACY.md).

MIT licensed; see [LICENSE](LICENSE). Independent integration, not affiliated with Docling or Dify. Report bugs through [GitHub Issues](https://github.com/vovapi/dify-docling-remote/issues) without sensitive documents or credentials. Report security issues privately to the repository owner.
