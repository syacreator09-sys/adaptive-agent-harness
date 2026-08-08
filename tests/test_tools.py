import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from factory.agents import AgentRegistry
from factory.router import AdaptiveRouter
from factory.tools import ToolRegistry, ToolRouter


class AdaptiveToolTests(unittest.TestCase):
    def test_claude_web_capability_exposes_real_builtins(self):
        result=ToolRegistry.resolve(["web","files"],discovered={},provider="claude")
        self.assertEqual(result["missing"],[])
        self.assertIn("WebSearch",result["provider_tools"])
        self.assertIn("WebFetch",result["provider_tools"])
        self.assertIn("Read",result["provider_tools"])

    def test_codex_web_is_not_falsely_claimed_without_adapter(self):
        result=ToolRegistry.resolve(["web","files"],discovered={},provider="codex")
        self.assertIn("web",result["missing"])
        self.assertNotIn("files",result["missing"])

    def test_media_adapter_requires_shell_and_is_selected_when_connected(self):
        discovered={
            "adapter:image":{"available":True,"path":"/opt/aah/image-adapter"},
        }
        no_shell=ToolRegistry.resolve(["image"],discovered,provider="claude")
        self.assertIn("image",no_shell["missing"])
        with_shell=ToolRegistry.resolve(["image","shell"],discovered,provider="claude")
        self.assertEqual(with_shell["selected"]["image"],"/opt/aah/image-adapter")
        self.assertNotIn("image",with_shell["missing"])

    def test_content_request_infers_media_requirement(self):
        agent=AgentRegistry().get("content_producer")
        router=ToolRouter(discovered={})
        result=router.for_agent("content_producer",agent,{"mode":"build"},"claude",{"request":"crea un carrusel de 6 imágenes"})
        self.assertIn("image",result["required"])
        self.assertIn("image",result["missing"])

    def test_research_roles_prefer_claude_when_both_are_ready(self):
        router=AdaptiveRouter({
            "claude":{"available":True,"authenticated":True},
            "codex":{"available":True,"authenticated":True},
        })
        result=router.assign_roles(["researcher","fact_checker"])
        self.assertEqual(result["researcher"]["provider"],"claude")
        self.assertEqual(result["fact_checker"]["provider"],"claude")


if __name__=="__main__":
    unittest.main()
