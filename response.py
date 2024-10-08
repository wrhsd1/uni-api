import json
import httpx
from datetime import datetime

from log_config import logger


async def generate_sse_response(timestamp, model, content=None, tools_id=None, function_call_name=None, function_call_content=None, role=None, tokens_use=None, total_tokens=None):
    sample_data = {
        "id": "chatcmpl-9ijPeRHa0wtyA2G8wq5z8FC3wGMzc",
        "object": "chat.completion.chunk",
        "created": timestamp,
        "model": model,
        "system_fingerprint": "fp_d576307f90",
        "choices": [
            {
                "index": 0,
                "delta": {"content": content},
                "logprobs": None,
                "finish_reason": None
            }
        ],
        "usage": None
    }
    if function_call_content:
        sample_data["choices"][0]["delta"] = {"tool_calls":[{"index":0,"function":{"arguments": function_call_content}}]}
    if tools_id and function_call_name:
        sample_data["choices"][0]["delta"] = {"tool_calls":[{"index":0,"id": tools_id,"type":"function","function":{"name": function_call_name, "arguments":""}}]}
        # sample_data["choices"][0]["delta"] = {"tool_calls":[{"index":0,"function":{"id": tools_id, "name": function_call_name}}]}
    if role:
        sample_data["choices"][0]["delta"] = {"role": role, "content": ""}
    json_data = json.dumps(sample_data, ensure_ascii=False)

    # 构建SSE响应
    sse_response = f"data: {json_data}\n\n"

    return sse_response

async def fetch_gemini_response_stream(client, url, headers, payload, model):
    timestamp = datetime.timestamp(datetime.now())
    async with client.stream('POST', url, headers=headers, json=payload) as response:
        if response.status_code != 200:
            error_message = await response.aread()
            error_str = error_message.decode('utf-8', errors='replace')
            try:
                error_json = json.loads(error_str)
            except json.JSONDecodeError:
                error_json = error_str
            yield {"error": f"fetch_gpt_response_stream HTTP Error {response.status_code}", "details": error_json}
        buffer = ""
        revicing_function_call = False
        function_full_response = "{"
        need_function_call = False
        async for chunk in response.aiter_text():
            buffer += chunk
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                # print(line)
                if line and '\"text\": \"' in line:
                    try:
                        json_data = json.loads( "{" + line + "}")
                        content = json_data.get('text', '')
                        content = "\n".join(content.split("\\n"))
                        sse_string = await generate_sse_response(timestamp, model, content)
                        yield sse_string
                    except json.JSONDecodeError:
                        logger.error(f"无法解析JSON: {line}")

                if line and ('\"functionCall\": {' in line or revicing_function_call):
                    revicing_function_call = True
                    need_function_call = True
                    if ']' in line:
                        revicing_function_call = False
                        continue

                    function_full_response += line

        if need_function_call:
            function_call = json.loads(function_full_response)
            function_call_name = function_call["functionCall"]["name"]
            sse_string = await generate_sse_response(timestamp, model, content=None, tools_id="chatcmpl-9inWv0yEtgn873CxMBzHeCeiHctTV", function_call_name=function_call_name)
            yield sse_string
            function_full_response = json.dumps(function_call["functionCall"]["args"])
            sse_string = await generate_sse_response(timestamp, model, content=None, tools_id="chatcmpl-9inWv0yEtgn873CxMBzHeCeiHctTV", function_call_name=None, function_call_content=function_full_response)
            yield sse_string

async def fetch_vertex_claude_response_stream(client, url, headers, payload, model):
    timestamp = datetime.timestamp(datetime.now())
    async with client.stream('POST', url, headers=headers, json=payload) as response:
        if response.status_code != 200:
            error_message = await response.aread()
            error_str = error_message.decode('utf-8', errors='replace')
            try:
                error_json = json.loads(error_str)
            except json.JSONDecodeError:
                error_json = error_str
            yield {"error": f"fetch_gpt_response_stream HTTP Error {response.status_code}", "details": error_json}
        buffer = ""
        revicing_function_call = False
        function_full_response = "{"
        need_function_call = False
        async for chunk in response.aiter_text():
            buffer += chunk
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                logger.info(f"{line}")
                if line and '\"text\": \"' in line:
                    try:
                        json_data = json.loads( "{" + line + "}")
                        content = json_data.get('text', '')
                        content = "\n".join(content.split("\\n"))
                        sse_string = await generate_sse_response(timestamp, model, content)
                        yield sse_string
                    except json.JSONDecodeError:
                        logger.error(f"无法解析JSON: {line}")

                if line and ('\"type\": \"tool_use\"' in line or revicing_function_call):
                    revicing_function_call = True
                    need_function_call = True
                    if ']' in line:
                        revicing_function_call = False
                        continue

                    function_full_response += line

        if need_function_call:
            function_call = json.loads(function_full_response)
            function_call_name = function_call["name"]
            function_call_id = function_call["id"]
            sse_string = await generate_sse_response(timestamp, model, content=None, tools_id=function_call_id, function_call_name=function_call_name)
            yield sse_string
            function_full_response = json.dumps(function_call["input"])
            sse_string = await generate_sse_response(timestamp, model, content=None, tools_id=function_call_id, function_call_name=None, function_call_content=function_full_response)
            yield sse_string

async def fetch_gpt_response_stream(client, url, headers, payload, max_redirects=5):
    redirect_count = 0
    while redirect_count < max_redirects:
        # logger.info(f"fetch_gpt_response_stream: {url}")
        async with client.stream('POST', url, headers=headers, json=payload) as response:
            if response.status_code != 200:
                error_message = await response.aread()
                error_str = error_message.decode('utf-8', errors='replace')
                try:
                    error_json = json.loads(error_str)
                except json.JSONDecodeError:
                    error_json = error_str
                yield {"error": f"fetch_gpt_response_stream HTTP Error {response.status_code}", "details": error_json}
                return

            buffer = ""
            try:
                async for chunk in response.aiter_text():
                    # logger.info(f"chunk: {repr(chunk)}")
                    buffer += chunk
                    if chunk.startswith("<script"):
                        import re
                        redirect_match = re.search(r"window\.location\.href\s*=\s*'([^']+)'", chunk)
                        if redirect_match:
                            new_url = redirect_match.group(1)
                            # logger.info(f"new_url: {new_url}")
                            if not new_url.startswith('http'):
                                # 如果是相对路径，构造完整URL
                                # logger.info(url.split('/'))
                                base_url = '/'.join(url.split('/')[:3])
                                new_url = base_url + new_url
                            url = new_url
                            # logger.info(f"new_url: {new_url}")
                            redirect_count += 1
                            break
                    redirect_count = 0
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        # logger.info("line: %s", repr(line))
                        if line and line != "data: " and line != "data:" and not line.startswith(": "):
                            yield line + "\n"
            except httpx.RemoteProtocolError as e:
                yield {"error": f"fetch_gpt_response_stream RemoteProtocolError {e.__class__.__name__}", "details": str(e)}
                return
        if redirect_count == 0:
            return

    yield {"error": "Too many redirects", "details": f"Reached maximum of {max_redirects} redirects"}

async def fetch_claude_response_stream(client, url, headers, payload, model):
    timestamp = datetime.timestamp(datetime.now())
    async with client.stream('POST', url, headers=headers, json=payload) as response:
        if response.status_code != 200:
            error_message = await response.aread()
            error_str = error_message.decode('utf-8', errors='replace')
            try:
                error_json = json.loads(error_str)
            except json.JSONDecodeError:
                error_json = error_str
            yield {"error": f"fetch_claude_response_stream HTTP Error {response.status_code}", "details": error_json}
        buffer = ""
        async for chunk in response.aiter_text():
            # logger.info(f"chunk: {repr(chunk)}")
            buffer += chunk
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                # logger.info(line)

                if line.startswith("data:"):
                    line = line[5:]
                    if line.startswith(" "):
                        line = line[1:]
                    resp: dict = json.loads(line)
                    message = resp.get("message")
                    if message:
                        tokens_use = resp.get("usage")
                        role = message.get("role")
                        if role:
                            sse_string = await generate_sse_response(timestamp, model, None, None, None, None, role)
                            yield sse_string
                        if tokens_use:
                            total_tokens = tokens_use["input_tokens"] + tokens_use["output_tokens"]
                            # print("\n\rtotal_tokens", total_tokens)
                    tool_use = resp.get("content_block")
                    tools_id = None
                    function_call_name = None
                    if tool_use and "tool_use" == tool_use['type']:
                        # print("tool_use", tool_use)
                        tools_id = tool_use["id"]
                        if "name" in tool_use:
                            function_call_name = tool_use["name"]
                            sse_string = await generate_sse_response(timestamp, model, None, tools_id, function_call_name, None)
                            yield sse_string
                    delta = resp.get("delta")
                    # print("delta", delta)
                    if not delta:
                        continue
                    if "text" in delta:
                        content = delta["text"]
                        sse_string = await generate_sse_response(timestamp, model, content, None, None)
                        yield sse_string
                    if "partial_json" in delta:
                        # {"type":"input_json_delta","partial_json":""}
                        function_call_content = delta["partial_json"]
                        sse_string = await generate_sse_response(timestamp, model, None, None, None, function_call_content)
                        yield sse_string

async def fetch_response(client, url, headers, payload):
    try:
        response = await client.post(url, headers=headers, json=payload)
        return response.json()
    except httpx.ConnectError as e:
        return {"error": f"500", "details": "fetch_response Connect Error"}
    except httpx.ReadTimeout as e:
        return {"error": f"500", "details": "fetch_response Read Response Timeout"}

async def fetch_response_stream(client, url, headers, payload, engine, model):
    try:
        if engine == "gemini" or (engine == "vertex" and "gemini" in model):
            async for chunk in fetch_gemini_response_stream(client, url, headers, payload, model):
                yield chunk
        elif engine == "claude" or (engine == "vertex" and "claude" in model):
            async for chunk in fetch_claude_response_stream(client, url, headers, payload, model):
                yield chunk
        elif engine == "gpt":
            async for chunk in fetch_gpt_response_stream(client, url, headers, payload):
                yield chunk
        elif engine == "openrouter":
            async for chunk in fetch_gpt_response_stream(client, url, headers, payload):
                yield chunk
        else:
            raise ValueError("Unknown response")
    except httpx.ConnectError as e:
        yield {"error": f"500", "details": "fetch_response_stream Connect Error"}
    except httpx.ReadTimeout as e:
        yield {"error": f"500", "details": "fetch_response_stream Read Response Timeout"}