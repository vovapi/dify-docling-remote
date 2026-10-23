from dify_plugin import Tool
from engine.client import ServeClient


class ServerInfoTool(Tool):
    def _invoke(self, tool_parameters):
        with ServeClient(self.runtime.credentials) as client:
            result = client.health()
        yield self.create_json_message(result)
        yield self.create_text_message('Docling Serve is reachable.')
