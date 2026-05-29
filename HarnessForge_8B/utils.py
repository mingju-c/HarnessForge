#!/usr/bin/env python
# coding=utf-8
# Copyright 2025 The OPPO Inc. PersonalAI team. All rights reserved.
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

import json
import yaml
from typing import List, Dict
from openai import OpenAI, OpenAIError

def read_jsonl(infile):
    data = []
    with open(infile, 'r', encoding='utf-8') as f:
        for line in f:
            data.append(json.loads(line))
    return data

def write_jsonl(outfile, data, mode='w'):
    with open(outfile, mode, encoding='utf-8') as f:
        for line in data:
            f.write(json.dumps(line, ensure_ascii=False) + '\n')

def read_json(infile):
    with open(infile, 'r', encoding='utf-8') as f:
        return json.load(f)

def write_json(outfile, data, mode='w'):
    with open(outfile, mode, encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def read_txt(infile):
    with open(infile, 'r', encoding='utf-8') as f:
        return f.read()

def write_txt(outfile, data, mode='w'):
    with open(outfile, mode, encoding='utf-8') as f:
        f.write(data)

def load_yaml(infile):
    with open(infile, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def write_yaml(outfile, data, mode='w'):
    with open(outfile, mode, encoding='utf-8') as f:
        yaml.dump(data, f, allow_unicode=True)

def safe_json_loads(text):
    text = text.lstrip("```json").rstrip("```").strip()
    try:
        return json.loads(text)
    except Exception as e:
        return str(text)
    
def openai_service(
    messages: List[Dict[str, str]],
    api_key: str,
    base_url: str,
    model: str,
    timeout: int
) -> str:
    if not all([api_key, base_url, model]):
        missing = []
        if not api_key:
            missing.append("api_key")
        if not base_url:
            missing.append("base_url")
        if not model:
            missing.append("model")
        raise ValueError(f"Missing required parameters: {', '.join(missing)}")

    try:
        client = OpenAI(
            api_key=api_key,
            base_url=base_url
        )

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=16000,
            timeout=timeout
        )
        
        if response.choices:
            return response.choices[0].message.content or ""
            
        return ""
        
    except OpenAIError as e:
        print(f"OpenAI API error occurred: {str(e)}")
        raise
    except Exception as e:
        print(f"Unexpected error in OpenAI service: {str(e)}")
        raise

def run_llm_prompt(model, prompt, developer_prompt=None, only_return_msg=False, return_json=False, max_retries=3):
    messages = []
    if developer_prompt:
        developer_text = {
            "role": "system",
            "content": [
                {
                    "type": "text",
                    "text": developer_prompt
                }
            ]
        }
        messages.append(developer_text)

    messages.append({
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": f"{prompt}",

            }
        ],
    }, )

    if only_return_msg:
        return messages
    else:
        last_error = None
        for _ in range(max_retries):
            try:
                response = model(messages)
                return safe_json_loads(response.content) if return_json else response.content
            except Exception as e:
                last_error = f"[run_llm_prompt] error: {e}"
        raise Exception(str(last_error))
        

def run_llm_msg(model, msg, prompt, developer_prompt=None, only_return_msg=False, return_json=False, max_retries=3):
    messages = []
    if developer_prompt:
        developer_text = {
            "role": "system",
            "content": [
                {
                    "type": "text",
                    "text": developer_prompt
                }
            ]
        }
        messages.append(developer_text)

    for id, prompt in enumerate(msg):
        if id % 2 == 0:
            messages.append({"role": "user", "content": [
                {"type": "text", "text": f"{prompt}"}]})
        else:
            messages.append({"role": "assistant", "content": [
                {"type": "text", "text": f"{prompt}"}]})
    
    if only_return_msg:
        return messages
    else:
        last_error = None
        for _ in range(max_retries):
            try:
                response = model(messages)
                return safe_json_loads(response.content) if return_json else response.content
            except Exception as e:
                last_error = f"[run_llm_msg] error: {e}"
        raise Exception(str(last_error))
        

