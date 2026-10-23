# Privacy policy

Effective date: October 21, 2026.

Docling Remote sends uploaded document bytes, filenames and selected conversion/chunking options from Dify to the administrator-configured Docling Serve URL. If configured, the API key is sent as the `X-Api-Key` header to that server. Conversion results are returned to Dify as text, JSON and ZIP files.

The plugin developer collects no user data and operates no conversion or analytics endpoint. The plugin does not persist documents to its own filesystem and does not intentionally log document bodies or credentials. Processing uses memory. The Dify file SDK may retrieve uploaded files from Dify storage. Dify may store workflow inputs, outputs and uploaded/generated files. Serve may store tasks/results, log requests or download model/tokenizer files according to its configuration. Administrators must review the policies of those services and configure retention and access controls.

Private HTTP(S) server addresses are explicitly supported. Only provider administrators choose the destination; workflow document inputs cannot change it. Redirects and environment proxies are disabled, TLS verification is enabled, and raw server error bodies are suppressed. This policy cannot govern how the configured server handles content. Use a trusted instance and transport appropriate to your network.

Questions and issues: [GitHub Issues](https://github.com/vovapi/dify-docling-remote/issues). Do not include sensitive documents or API keys in reports.
