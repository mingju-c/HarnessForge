#!/usr/bin/env python
# coding=utf-8

# Copyright 2024 The HuggingFace Inc. team. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Portions of this file are modifications by OPPO PersonalAI Team.
# Licensed under the Apache License, Version 2.0.

import json
import logging
import os
from copy import deepcopy
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Union

try:
    from huggingface_hub import InferenceClient
    from huggingface_hub.utils import is_torch_available
except ImportError:
    InferenceClient = None

    def is_torch_available():
        return False

try:
    from PIL import Image
except ImportError:
    Image = None

try:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
except ImportError:
    torch = None
    AutoModelForCausalLM = None
    AutoTokenizer = None

try:
    from openai import (
        BadRequestError,
        APIStatusError,
        APIConnectionError,
        OpenAIError,
    )
except ImportError:
    class OpenAIError(Exception):
        pass

    class BadRequestError(OpenAIError):
        pass

    class APIStatusError(OpenAIError):
        pass

    class APIConnectionError(OpenAIError):
        pass
import time

from .tools import Tool
from .utils import encode_image_base64, make_image_url


logger = logging.getLogger(__name__)

DEFAULT_JSONAGENT_REGEX_GRAMMAR = {
    "type": "regex",
    "value": 'Thought: .+?\\nAction:\\n\\{\\n\\s{4}"action":\\s"[^"\\n]+",\\n\\s{4}"action_input":\\s"[^"\\n]+"\\n\\}\\n<end_code>',
}

DEFAULT_CODEAGENT_REGEX_GRAMMAR = {
    "type": "regex",
    "value": "Thought: .+?\\nCode:\\n```(?:py|python)?\\n(?:.|\\s)+?\\n```<end_code>",
}


class EmptyContentError(Exception):
    def __init__(self, response):
        self.response = response
        super().__init__(f"Empty content in response: {response}")


def _has_non_empty_message_content(content: Any) -> bool:
    if content is None:
        return False
    if isinstance(content, str):
        return bool(content.strip())
    if isinstance(content, list):
        return any(_has_non_empty_message_content(item) for item in content)
    if isinstance(content, dict):
        for key in ("text", "content", "value"):
            if key in content and _has_non_empty_message_content(content[key]):
                return True
        return bool(content)
    return bool(content)


def _retry_delay_for_attempt(attempt: int, *, base_delay: int = 2, max_delay: int = 30) -> int:
    return min(base_delay * (2 ** attempt), max_delay)



def get_dict_from_nested_dataclasses(obj, ignore_key=None):
    def convert(obj):
        if hasattr(obj, "__dataclass_fields__"):
            return {k: convert(v) for k, v in asdict(obj).items() if k != ignore_key}
        return obj

    return convert(obj)


@dataclass
class ChatMessageToolCallDefinition:
    arguments: Any
    name: str
    description: Optional[str] = None

    @classmethod
    def from_hf_api(cls, tool_call_definition) -> "ChatMessageToolCallDefinition":
        return cls(
            arguments=tool_call_definition.arguments,
            name=tool_call_definition.name,
            description=tool_call_definition.description,
        )


@dataclass
class ChatMessageToolCall:
    function: ChatMessageToolCallDefinition
    id: str
    type: str

    @classmethod
    def from_hf_api(cls, tool_call) -> "ChatMessageToolCall":
        return cls(
            function=ChatMessageToolCallDefinition.from_hf_api(tool_call.function),
            id=tool_call.id,
            type=tool_call.type,
        )


@dataclass
class ChatMessage:
    role: str
    content: Optional[str] = None
    reasoning_content: Optional[str] = None
    tool_calls: Optional[List[ChatMessageToolCall]] = None
    raw: Optional[Any] = None  # Stores the raw output from the API

    def model_dump_json(self):
        return json.dumps(get_dict_from_nested_dataclasses(self, ignore_key="raw"))

    @classmethod
    def from_hf_api(cls, message, raw) -> "ChatMessage":
        tool_calls = None
        if getattr(message, "tool_calls", None) is not None:
            tool_calls = [ChatMessageToolCall.from_hf_api(tool_call) for tool_call in message.tool_calls]
        return cls(role=message.role, content=message.content, tool_calls=tool_calls, reasoning_content=message.reasoning_content, raw=raw)

    @classmethod
    def from_dict(cls, data: dict) -> "ChatMessage":
        if data.get("tool_calls"):
            # ** ** ** ** ** ** ** *0307hhy ** ** ** ** *
            tool_calls = [
                ChatMessageToolCall(
                    function=ChatMessageToolCallDefinition(
                        **{k: v for k, v in tc["function"].items() if k != "parameters"}
                    ),
                    id=tc["id"],
                    type=tc["type"]
                )
                for tc in data["tool_calls"]
            ]
            data["tool_calls"] = tool_calls
        return cls(**data)

    def dict(self):
        return json.dumps(get_dict_from_nested_dataclasses(self))


def parse_json_if_needed(arguments: Union[str, dict]) -> Union[str, dict]:
    if isinstance(arguments, dict):
        return arguments
    else:
        try:
            return json.loads(arguments)
        except Exception:
            return arguments


def parse_tool_args_if_needed(message: ChatMessage) -> ChatMessage:
    if message.tool_calls is not None:
        for tool_call in message.tool_calls:
            tool_call.function.arguments = parse_json_if_needed(tool_call.function.arguments)
    return message


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL_CALL = "tool-call"
    TOOL_RESPONSE = "tool-response"

    @classmethod
    def roles(cls):
        return [r.value for r in cls]


tool_role_conversions = {
    MessageRole.TOOL_CALL: MessageRole.ASSISTANT,
    MessageRole.TOOL_RESPONSE: MessageRole.USER,
}


def get_tool_json_schema(tool: Tool) -> Dict:
    properties = deepcopy(tool.inputs)
    required = []
    for key, value in properties.items():
        if value["type"] == "any":
            value["type"] = "string"
        if not ("nullable" in value and value["nullable"]):
            required.append(key)
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


def remove_stop_sequences(content: str, stop_sequences: List[str]) -> str:
    for stop_seq in stop_sequences:
        if content[-len(stop_seq) :] == stop_seq:
            content = content[: -len(stop_seq)]
    return content


def get_clean_message_list(
    message_list: List[Dict[str, str]],
    role_conversions: Dict[MessageRole, MessageRole] = {},
    convert_images_to_image_urls: bool = False,
    flatten_messages_as_text: bool = False,
) -> List[Dict[str, str]]:
    """
    Subsequent messages with the same role will be concatenated to a single message.
    output_message_list is a list of messages that will be used to generate the final message that is chat template compatible with transformers LLM chat template.

    Args:
        message_list (`list[dict[str, str]]`): List of chat messages.
        role_conversions (`dict[MessageRole, MessageRole]`, *optional* ): Mapping to convert roles.
        convert_images_to_image_urls (`bool`, default `False`): Whether to convert images to image URLs.
        flatten_messages_as_text (`bool`, default `False`): Whether to flatten messages as text.
    """
    output_message_list = []
    message_list = deepcopy(message_list)  # Avoid modifying the original list
    for message in message_list:
        role = message["role"]
        if role not in MessageRole.roles():
            raise ValueError(f"Incorrect role {role}, only {MessageRole.roles()} are supported for now.")

        if role in role_conversions:
            message["role"] = role_conversions[role]
        # encode images if needed
        if isinstance(message["content"], list):
            for element in message["content"]:
                if element["type"] == "image":
                    assert not flatten_messages_as_text, f"Cannot use images with {flatten_messages_as_text=}"
                    if convert_images_to_image_urls:
                        element.update(
                            {
                                "type": "image_url",
                                "image_url": {"url": make_image_url(encode_image_base64(element.pop("image")))},
                            }
                        )
                    else:
                        element["image"] = encode_image_base64(element["image"])

        if len(output_message_list) > 0 and message["role"] == output_message_list[-1]["role"]:
            assert isinstance(message["content"], list), "Error: wrong content:" + str(message["content"])
            if flatten_messages_as_text:
                output_message_list[-1]["content"] += message["content"][0]["text"]
            else:
                output_message_list[-1]["content"] += message["content"]
        else:
            if flatten_messages_as_text:
                content = message["content"][0]["text"]
            else:
                content = message["content"]
            output_message_list.append({"role": message["role"], "content": content})
    return output_message_list


class Model:
    def __init__(self, **kwargs):
        # Last call statistics (single API call)
        self.last_input_token_count = None
        self.last_output_token_count = None
        # Task-level cumulative statistics (multiple API calls in one task)
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_api_calls = 0
        self.kwargs = kwargs

    def _prepare_completion_kwargs(
        self,
        messages: List[Dict[str, str]],
        stop_sequences: Optional[List[str]] = None,
        grammar: Optional[str] = None,
        tools_to_call_from: Optional[List[Tool]] = None,
        custom_role_conversions: Optional[Dict[str, str]] = None,
        convert_images_to_image_urls: bool = False,
        flatten_messages_as_text: bool = False,
        **kwargs,
    ) -> Dict:
        """
        Prepare parameters required for model invocation, handling parameter priorities.

        Parameter priority from high to low:
        1. Explicitly passed kwargs
        2. Specific parameters (stop_sequences, grammar, etc.)
        3. Default values in self.kwargs
        """
        # Clean and standardize the message list
        messages = get_clean_message_list(
            messages,
            role_conversions=custom_role_conversions or tool_role_conversions,
            convert_images_to_image_urls=convert_images_to_image_urls,
            flatten_messages_as_text=flatten_messages_as_text,
        )

        # Use self.kwargs as the base configuration
        completion_kwargs = {
            **self.kwargs,
            "messages": messages,
        }

        # Handle specific parameters
        if stop_sequences is not None:
            completion_kwargs["stop"] = stop_sequences
        if grammar is not None:
            completion_kwargs["grammar"] = grammar

        # Handle tools parameter
        if tools_to_call_from:
            completion_kwargs.update(
                {
                    "tools": [get_tool_json_schema(tool) for tool in tools_to_call_from],
                    "tool_choice": "required",
                }
            )

        # Finally, use the passed-in kwargs to override all settings
        completion_kwargs.update(kwargs)

        return completion_kwargs

    def reset_total_counts(self):
        """Reset cumulative token counts for a new task."""
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_api_calls = 0

    def get_token_counts(self) -> Dict[str, int]:
        return {
            "input_token_count": self.last_input_token_count,
            "output_token_count": self.last_output_token_count,
        }

    def get_total_counts(self) -> Dict[str, int]:
        return {
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": self.total_input_tokens + self.total_output_tokens,
            "total_api_calls": self.total_api_calls,
        }

    def __call__(
        self,
        messages: List[Dict[str, str]],
        stop_sequences: Optional[List[str]] = None,
        grammar: Optional[str] = None,
        tools_to_call_from: Optional[List[Tool]] = None,
        **kwargs,
    ) -> ChatMessage:
        """Process the input messages and return the model's response.

        Parameters:
            messages (`List[Dict[str, str]]`):
                A list of message dictionaries to be processed. Each dictionary should have the structure `{"role": "user/system", "content": "message content"}`.
            stop_sequences (`List[str]`, *optional*):
                A list of strings that will stop the generation if encountered in the model's output.
            grammar (`str`, *optional*):
                The grammar or formatting structure to use in the model's response.
            tools_to_call_from (`List[Tool]`, *optional*):
                A list of tools that the model can use to generate responses.
            **kwargs:
                Additional keyword arguments to be passed to the underlying model.

        Returns:
            `ChatMessage`: A chat message object containing the model's response.
        """
        pass  # To be implemented in child classes!

    def to_dict(self) -> Dict:
        """
        Converts the model into a JSON-compatible dictionary.
        """
        model_dictionary = {
            **self.kwargs,
            "last_input_token_count": self.last_input_token_count,
            "last_output_token_count": self.last_output_token_count,
            "model_id": self.model_id,
        }
        for attribute in [
            "custom_role_conversion",
            "temperature",
            "max_tokens",
            "provider",
            "timeout",
            "api_base",
            "torch_dtype",
            "device_map",
            "organization",
            "project",
            "azure_endpoint",
        ]:
            if hasattr(self, attribute):
                model_dictionary[attribute] = getattr(self, attribute)

        dangerous_attributes = ["token", "api_key"]
        for attribute_name in dangerous_attributes:
            if hasattr(self, attribute_name):
                print(
                    f"For security reasons, we do not export the `{attribute_name}` attribute of your model. Please export it manually."
                )
        return model_dictionary

    @classmethod
    def from_dict(cls, model_dictionary: Dict[str, Any]) -> "Model":
        model_instance = cls(
            **{
                k: v
                for k, v in model_dictionary.items()
                if k not in ["last_input_token_count", "last_output_token_count"]
            }
        )
        model_instance.last_input_token_count = model_dictionary.pop("last_input_token_count", None)
        model_instance.last_output_token_count = model_dictionary.pop("last_output_token_count", None)
        return model_instance


class OpenAIServerModel(Model):
    """This model connects to an OpenAI-compatible API server.

    Parameters:
        model_id (`str`):
            The model identifier to use on the server (e.g. "gpt-3.5-turbo").
        api_base (`str`, *optional*):
            The base URL of the OpenAI-compatible API server.
        api_key (`str`, *optional*):
            The API key to use for authentication.
        organization (`str`, *optional*):
            The organization to use for the API request.
        project (`str`, *optional*):
            The project to use for the API request.
        custom_role_conversions (`dict[str, str]`, *optional*):
            Custom role conversion mapping to convert message roles in others.
            Useful for specific models that do not support specific message roles like "system".
        **kwargs:
            Additional keyword arguments to pass to the OpenAI API.
    """

    def __init__(
        self,
        model_id: str,
        api_base: Optional[str] = None,
        api_key: Optional[str] = None,
        organization: Optional[str] | None = None,
        project: Optional[str] | None = None,
        custom_role_conversions: Optional[Dict[str, str]] = None,
        **kwargs,
    ):
        try:
            import openai
        except ModuleNotFoundError:
            raise ModuleNotFoundError(
                "Please install 'openai' extra to use OpenAIServerModel: `pip install 'smolagents[openai]'`"
            ) from None

        super().__init__(**kwargs)
        self.model_id = model_id
        self.api_base = api_base
        self.client = openai.OpenAI(
            base_url=api_base,
            api_key=api_key,
            organization=organization,
            project=project,
        )
        self.custom_role_conversions = custom_role_conversions

    def _should_disable_thinking_for_non_streaming(self, completion_kwargs: Dict[str, Any]) -> bool:
        model_id = self.model_id.lower()
        is_streaming = bool(completion_kwargs.get("stream"))
        is_qwen3_open_source = model_id.startswith("qwen3-")
        return is_qwen3_open_source and not is_streaming

    @staticmethod
    def truncate_content_based_on_stop_sequences(content: str, stop_sequences: List[str]) -> str:
        if not stop_sequences:
            return content
        # 在stop_seq之后截断content
        for stop_seq in stop_sequences:
            index = content.find(stop_seq)
            if index != -1:
                content = content[:index + len(stop_seq)]
                break  # Only keep the first match
        return content

    @staticmethod
    def remove_think_tags(content: str) -> str:
        """Remove think-related tags like <think>...</think> and <redacted_reasoning/>."""
        if not content:
            return content
        import re
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL | re.IGNORECASE)
        content = re.sub(r"<think\\s*/>", "", content, flags=re.IGNORECASE)
        content = re.sub(r"<redacted_reasoning\\s*/>", "", content, flags=re.IGNORECASE)
        content = re.sub(r"<think\\b[^>]*>.*$", "", content, flags=re.DOTALL | re.IGNORECASE)
        return content.strip()

    def __call__(
        self,
        messages: List[Dict[str, str]],
        stop_sequences: Optional[List[str]] = None,
        grammar: Optional[str] = None,
        tools_to_call_from: Optional[List[Tool]] = None,
        **kwargs,
    ) -> ChatMessage:
        completion_kwargs = self._prepare_completion_kwargs(
            messages=messages,
            stop_sequences=stop_sequences,
            grammar=grammar,
            tools_to_call_from=tools_to_call_from,
            model=self.model_id,
            custom_role_conversions=self.custom_role_conversions,
            convert_images_to_image_urls=True,
            **kwargs,
        )

        # Check if model_id contains 'o3' or 'o4'
        if 'o3' in self.model_id.lower() or 'o4' in self.model_id.lower():
            # Remove stop_sequences from completion_kwargs
            completion_kwargs.pop('stop', None)

        # For reasoning models without explicit tools, disable tool_choice to avoid MALFORMED_FUNCTION_CALL
        # This includes cleaning up any tools/tool_choice that might come from self.kwargs or **kwargs
        if tools_to_call_from is None:
            if any(keyword in self.model_id.lower() for keyword in ['gemini', 'o1', 'o3']):
                completion_kwargs.pop('tool_choice', None)
                completion_kwargs.pop('tools', None)

        if self._should_disable_thinking_for_non_streaming(completion_kwargs):
            extra_body = dict(completion_kwargs.get("extra_body") or {})
            extra_body["enable_thinking"] = False
            chat_template_kwargs = dict(extra_body.get("chat_template_kwargs") or {})
            chat_template_kwargs["enable_thinking"] = False
            extra_body["chat_template_kwargs"] = chat_template_kwargs
            completion_kwargs["extra_body"] = extra_body

        # response = self.client.chat.completions.create(**completion_kwargs)

        max_retries = 5
        retry_delay = 5  # seconds
        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(**completion_kwargs)

                self.last_input_token_count = response.usage.prompt_tokens
                self.last_output_token_count = response.usage.completion_tokens
                self.total_input_tokens += response.usage.prompt_tokens
                self.total_output_tokens += response.usage.completion_tokens
                self.total_api_calls += 1

                assistant_message = response.choices[0].message
                has_message_content = _has_non_empty_message_content(getattr(assistant_message, "content", None))
                has_tool_calls = bool(getattr(assistant_message, "tool_calls", None))
                if not has_message_content and not has_tool_calls:
                    raise EmptyContentError(response)

                message = ChatMessage.from_dict(
                    assistant_message.model_dump(include={"role", "content", "tool_calls", "reasoning_content"})
                )
                message.raw = {
                    "input": completion_kwargs.get("messages", []),
                    "output": response.model_dump() if hasattr(response, "model_dump") else str(response)
                }

                # If model_id contains 'o3' or 'o4', manually truncate content based on stop_sequences
                if 'o3' in self.model_id.lower() or 'o4' in self.model_id.lower():
                    message.content = self.truncate_content_based_on_stop_sequences(message.content, stop_sequences)

                if message.content:
                    message.content = self.remove_think_tags(message.content)

                if tools_to_call_from is not None:
                    return parse_tool_args_if_needed(message)
                return message
            except BadRequestError as e:
                logger.error("Bad Request Error: %s", e)
                raise
            except APIConnectionError as e:
                if attempt < max_retries - 1:
                    logging.warning(f"Network error occurred: {e}. Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    logging.error(f"Failed to complete request after {max_retries} retries.")
                    raise
            except (APIStatusError, EmptyContentError) as e:
                if attempt < max_retries - 1:
                    backoff = _retry_delay_for_attempt(attempt)
                    logging.warning(
                        f"API status error occurred: {e}. "
                        f"Retrying in {backoff} seconds ({attempt + 1}/{max_retries})..."
                    )
                    time.sleep(backoff)
                else:
                    logging.error(f"Failed to complete request after {max_retries} retries.")
                    raise
            except OpenAIError as e:
                logging.error(f"API error occurred: {e}.")
                raise
            except Exception as e:
                logging.error(f"An unexpected error occurred: {e}.")
                raise

__all__ = [
    "MessageRole",
    "tool_role_conversions",
    "get_clean_message_list",
    "Model",
    "OpenAIServerModel",
    "LocalTransformersModel",
    "ChatMessage",
]


class LocalTransformersModel(Model):
    """本地加载 Transformers 模型的类"""

    def __init__(
        self,
        model_id: str,
        device: str = "cuda",
        torch_dtype: str = "float16",
        trust_remote_code: bool = True,
        **kwargs,
    ):
        if AutoModelForCausalLM is None or AutoTokenizer is None:
            raise ImportError("请安装 transformers 和 torch: pip install transformers torch")

        super().__init__(**kwargs)
        # 如果带有 local: 前缀，去掉它
        self.model_id = model_id.replace("local:", "") if model_id.startswith("local:") else model_id
        self.device = device
        
        dtype = torch.float16 if torch_dtype == "float16" else torch.bfloat16
        
        logger.info(f"正在从本地加载模型: {self.model_id}")
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_id, trust_remote_code=trust_remote_code)
        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_id,
            torch_dtype=dtype,
            device_map=device,
            trust_remote_code=trust_remote_code
        )
        logger.info("本地模型加载完成。")

    def __call__(
        self,
        messages: List[Dict[str, str]],
        stop_sequences: Optional[List[str]] = None,
        grammar: Optional[str] = None,
        tools_to_call_from: Optional[List[Tool]] = None,
        **kwargs,
    ) -> ChatMessage:
        input_ids = self.tokenizer.apply_chat_template(
            messages,
            add_generation_prompt=True,
            return_tensors="pt"
        ).to(self.device)

        generate_kwargs = {
            "input_ids": input_ids,
            "max_new_tokens": kwargs.get("max_new_tokens", 4096),
            "do_sample": kwargs.get("do_sample", True),
            "temperature": kwargs.get("temperature", 0.7),
            "pad_token_id": self.tokenizer.eos_token_id,
        }
        
        if stop_sequences:
            generate_kwargs["stop_strings"] = stop_sequences
            generate_kwargs["tokenizer"] = self.tokenizer

        outputs = self.model.generate(**generate_kwargs)
        generated_text = self.tokenizer.decode(outputs[0][input_ids.shape[-1]:], skip_special_tokens=True)

        self.last_input_token_count = input_ids.shape[-1]
        self.last_output_token_count = outputs.shape[-1] - input_ids.shape[-1]
        self.total_input_tokens += self.last_input_token_count
        self.total_output_tokens += self.last_output_token_count
        self.total_api_calls += 1
        
        return ChatMessage(role="assistant", content=generated_text)
