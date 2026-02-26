"""
Realtime Spec Generator - Generates AsyncAPI 2.6 specifications for WebSocket/real-time features.

Identifies real-time requirements and derives WebSocket channels, events, and message schemas.
Produces AsyncAPI YAML output for code generation tools.
"""

import os
import json
import re
import time
import yaml
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from dataclasses_json import dataclass_json
from datetime import datetime

# Try to import OpenAI, fall back gracefully
try:
    from openai import AsyncOpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

# Import LLM logger
from requirements_engineer.core.llm_logger import get_llm_logger, log_llm_call


# Keywords that indicate real-time requirements
RT_KEYWORDS = [
    # English
    "real-time", "realtime", "real time", "live", "instant", "push",
    "notification", "typing", "online", "presence", "message", "chat",
    "call", "stream", "websocket", "socket", "event", "broadcast",
    "sync", "update in real", "status update",
    # German
    "echtzeit", "benachrichtigung", "nachricht", "anruf", "sofort",
    "tippen", "zustellung", "gelesen", "status", "verbindung",
]


@dataclass_json
@dataclass
class ChannelMessage:
    """A message type for a WebSocket channel."""
    name: str
    description: str = ""
    fields: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    # e.g. {"content": {"type": "string"}, "sender_id": {"type": "string"}}


@dataclass_json
@dataclass
class Channel:
    """A WebSocket channel definition."""
    name: str  # e.g. "chat/messages"
    description: str = ""
    subscribe: Optional[ChannelMessage] = None  # Server -> Client
    publish: Optional[ChannelMessage] = None  # Client -> Server
    parameters: Dict[str, str] = field(default_factory=dict)
    parent_requirement_id: str = ""


@dataclass_json
@dataclass
class RealtimeSpec:
    """Complete real-time/WebSocket specification."""
    title: str
    version: str = "1.0.0"
    channels: List[Channel] = field(default_factory=list)
    server_url: str = "wss://api.example.com/ws"
    protocol: str = "websocket"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


class RealtimeSpecGenerator:
    """
    Generates AsyncAPI 2.6 specifications for WebSocket/real-time features.

    The generator:
    1. Filters requirements that have real-time characteristics
    2. Derives WebSocket channels and message schemas via LLM
    3. Produces AsyncAPI 2.6 YAML specification
    """

    CHANNEL_PROMPT = """You are a real-time systems architect specializing in WebSocket APIs.

Given this requirement:
- ID: {req_id}
- Title: {title}
- Description: {description}

Derive WebSocket channels and events needed for real-time features.

Return JSON format:
{{
    "channels": [
        {{
            "name": "chat/messages",
            "description": "Real-time chat message delivery",
            "subscribe": {{
                "name": "ChatMessageReceived",
                "description": "Incoming message from another user",
                "fields": {{
                    "message_id": {{"type": "string", "description": "Unique message ID"}},
                    "sender_id": {{"type": "string", "description": "Sender user ID"}},
                    "content": {{"type": "string", "description": "Message content"}},
                    "timestamp": {{"type": "string", "format": "date-time"}}
                }}
            }},
            "publish": {{
                "name": "SendChatMessage",
                "description": "Send a new message",
                "fields": {{
                    "conversation_id": {{"type": "string"}},
                    "content": {{"type": "string"}},
                    "type": {{"type": "string", "enum": ["text", "image", "file"]}}
                }}
            }},
            "parameters": {{
                "conversation_id": "string"
            }}
        }}
    ]
}}

Guidelines:
- Use hierarchical channel names (e.g., "chat/messages", "user/presence", "call/signal")
- subscribe = events FROM server TO client (receiving)
- publish = events FROM client TO server (sending)
- Include all necessary fields with types
- Consider acknowledgment events where needed
- Only include channels directly related to the requirement

Return ONLY valid JSON."""

    def __init__(
        self,
        model_name: str = None,
        base_url: str = "https://openrouter.ai/api/v1",
        api_key: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        self.config = config or {}
        gen_config = self.config.get("generators", {}).get("realtime_spec", {})

        self.model_name = model_name or gen_config.get("model", "openai/gpt-4o-mini")
        self.temperature = gen_config.get("temperature", 0.5)
        self.max_tokens = gen_config.get("max_tokens", 6000)
        self.base_url = base_url
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        self.client = None

    async def initialize(self):
        """Initialize the OpenAI client."""
        if not HAS_OPENAI:
            raise ImportError("openai package required.")
        self.client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)

    async def _call_llm(self, prompt: str) -> str:
        if not self.client:
            await self.initialize()
        start_time = time.time()
        response = await self.client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": "You are a real-time systems architect. Return ONLY valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        latency_ms = int((time.time() - start_time) * 1000)
        response_text = response.choices[0].message.content.strip()
        log_llm_call(
            component="realtime_spec_generator",
            model=self.model_name,
            response=response,
            latency_ms=latency_ms,
            system_message="You are a real-time systems architect. Return ONLY valid JSON.",
            user_message=prompt,
            response_text=response_text,
        )
        return response_text

    def _extract_json(self, text: str) -> Dict[str, Any]:
        """Extract JSON from LLM response."""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        return {"channels": []}

    @staticmethod
    def filter_realtime_requirements(requirements: List) -> List:
        """Filter requirements that have real-time characteristics."""
        rt_reqs = []
        for req in requirements:
            title = getattr(req, "title", "").lower()
            desc = getattr(req, "description", "").lower()
            text = f"{title} {desc}"
            if any(kw in text for kw in RT_KEYWORDS):
                rt_reqs.append(req)
        return rt_reqs

    async def derive_channels(self, requirement) -> List[Channel]:
        """Derive WebSocket channels from a single requirement."""
        prompt = self.CHANNEL_PROMPT.format(
            req_id=requirement.requirement_id,
            title=requirement.title,
            description=requirement.description,
        )
        response = await self._call_llm(prompt)
        data = self._extract_json(response)

        channels = []
        for ch_data in data.get("channels", []):
            subscribe = None
            if sub := ch_data.get("subscribe"):
                subscribe = ChannelMessage(
                    name=sub.get("name", ""),
                    description=sub.get("description", ""),
                    fields=sub.get("fields", {}),
                )
            publish = None
            if pub := ch_data.get("publish"):
                publish = ChannelMessage(
                    name=pub.get("name", ""),
                    description=pub.get("description", ""),
                    fields=pub.get("fields", {}),
                )
            channel = Channel(
                name=ch_data.get("name", "unknown"),
                description=ch_data.get("description", ""),
                subscribe=subscribe,
                publish=publish,
                parameters=ch_data.get("parameters", {}),
                parent_requirement_id=requirement.requirement_id,
            )
            channels.append(channel)
        return channels

    async def generate_asyncapi_spec(
        self,
        requirements: List,
        title: str = "Realtime API",
        server_url: str = "wss://api.example.com/ws",
    ) -> str:
        """
        Generate AsyncAPI 2.6 YAML from real-time requirements.

        Returns empty string if no real-time requirements found.
        """
        rt_reqs = self.filter_realtime_requirements(requirements)
        if not rt_reqs:
            print("  [INFO] No real-time requirements found, skipping AsyncAPI generation")
            return ""

        print(f"  Found {len(rt_reqs)} real-time requirements")

        all_channels = []
        for i, req in enumerate(rt_reqs, 1):
            print(f"  [{i}/{len(rt_reqs)}] Deriving channels for: {req.title}")
            channels = await self.derive_channels(req)
            all_channels.extend(channels)
            print(f"    Derived {len(channels)} channels")

        if not all_channels:
            return ""

        spec = RealtimeSpec(
            title=title,
            channels=all_channels,
            server_url=server_url,
        )

        return self._to_asyncapi_yaml(spec)

    def _to_asyncapi_yaml(self, spec: RealtimeSpec) -> str:
        """Convert RealtimeSpec to AsyncAPI 2.6 YAML."""
        asyncapi = {
            "asyncapi": "2.6.0",
            "info": {
                "title": spec.title,
                "version": spec.version,
                "description": f"WebSocket API specification.\n\nGenerated: {spec.created_at}",
            },
            "servers": {
                "production": {
                    "url": spec.server_url,
                    "protocol": spec.protocol,
                }
            },
            "channels": {},
            "components": {"messages": {}, "schemas": {}},
        }

        for channel in spec.channels:
            ch_spec: Dict[str, Any] = {"description": channel.description}

            if channel.parameters:
                ch_spec["parameters"] = {
                    k: {"schema": {"type": v}} for k, v in channel.parameters.items()
                }

            if channel.subscribe:
                msg_name = channel.subscribe.name
                ch_spec["subscribe"] = {
                    "message": {"$ref": f"#/components/messages/{msg_name}"}
                }
                asyncapi["components"]["messages"][msg_name] = {
                    "name": msg_name,
                    "title": channel.subscribe.description or msg_name,
                    "payload": {
                        "type": "object",
                        "properties": channel.subscribe.fields,
                    },
                }

            if channel.publish:
                msg_name = channel.publish.name
                ch_spec["publish"] = {
                    "message": {"$ref": f"#/components/messages/{msg_name}"}
                }
                asyncapi["components"]["messages"][msg_name] = {
                    "name": msg_name,
                    "title": channel.publish.description or msg_name,
                    "payload": {
                        "type": "object",
                        "properties": channel.publish.fields,
                    },
                }

            asyncapi["channels"][channel.name] = ch_spec

        return yaml.dump(asyncapi, default_flow_style=False, allow_unicode=True, sort_keys=False)

    def to_markdown(self, spec_yaml: str) -> str:
        """Convert AsyncAPI YAML to markdown documentation."""
        if not spec_yaml:
            return ""

        spec = yaml.safe_load(spec_yaml)
        md = f"# {spec['info']['title']} - WebSocket API\n\n"
        md += f"**Version:** {spec['info']['version']}\n"
        md += f"**Protocol:** WebSocket\n\n"

        server = list(spec.get("servers", {}).values())[0] if spec.get("servers") else {}
        if server:
            md += f"**Server:** `{server.get('url', '')}`\n\n"

        md += "## Channels\n\n"
        for name, ch in spec.get("channels", {}).items():
            md += f"### `{name}`\n\n"
            md += f"{ch.get('description', '')}\n\n"

            if "subscribe" in ch:
                msg_ref = ch["subscribe"]["message"].get("$ref", "")
                msg_name = msg_ref.split("/")[-1]
                msg = spec.get("components", {}).get("messages", {}).get(msg_name, {})
                md += f"**Subscribe (Server -> Client):** `{msg_name}`\n\n"
                props = msg.get("payload", {}).get("properties", {})
                if props:
                    md += "| Field | Type | Description |\n|-------|------|-------------|\n"
                    for field_name, field_def in props.items():
                        md += f"| `{field_name}` | `{field_def.get('type', '')}` | {field_def.get('description', '')} |\n"
                    md += "\n"

            if "publish" in ch:
                msg_ref = ch["publish"]["message"].get("$ref", "")
                msg_name = msg_ref.split("/")[-1]
                msg = spec.get("components", {}).get("messages", {}).get(msg_name, {})
                md += f"**Publish (Client -> Server):** `{msg_name}`\n\n"
                props = msg.get("payload", {}).get("properties", {})
                if props:
                    md += "| Field | Type | Description |\n|-------|------|-------------|\n"
                    for field_name, field_def in props.items():
                        md += f"| `{field_name}` | `{field_def.get('type', '')}` | {field_def.get('description', '')} |\n"
                    md += "\n"

            md += "---\n\n"

        return md
