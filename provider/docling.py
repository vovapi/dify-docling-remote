from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from engine.client import ServeClient


class DoclingProvider(ToolProvider):
    def _validate_credentials(self, credentials):
        try:
            with ServeClient(credentials) as client:
                # Health is public; a protected request also validates the API key.
                client.health()
                client.request('GET', '/v1/status/poll/docling-credential-probe')
        except RuntimeError as exc:
            if 'HTTP 404;' in str(exc):
                return
            raise ToolProviderCredentialValidationError(str(exc)) from None
        except ValueError as exc:
            raise ToolProviderCredentialValidationError(str(exc)) from None
