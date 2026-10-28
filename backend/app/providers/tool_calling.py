"""Native tool protocols. Keep reasoning items for stateless Responses continuation."""
import asyncio
import json

from ..observability.usage import attach_usage_payload


async def openai_turn(provider, instructions, messages, tools):
    inputs = []
    for message in messages:
        if message["role"] == "assistant":
            inputs.extend(message["items"])
        elif message["role"] == "tool":
            inputs.append({"type": "function_call_output", "call_id": message["call_id"],
                           "output": message["content"]})
        else:
            content = [{"type": "input_text", "text": message["content"]}]
            for img in message.get("images", []):
                content.extend([{"type": "input_text", "text": f"Attachment #{img['id']}"},
                                {"type": "input_image", "image_url": img["data_url"]}])
            inputs.append({"role": "user", "content": content})
    response = await asyncio.to_thread(
        provider.client.responses.create, model=provider.model, instructions=instructions,
        input=inputs, tools=[{"type": "function", "name": t["name"], "description": t["description"],
                             "parameters": t["parameters"], "strict": False} for t in tools],
        tool_choice="required", parallel_tool_calls=False, store=False,
        include=["reasoning.encrypted_content"], max_output_tokens=7000, timeout=120,
    )
    if response.status != "completed":
        raise RuntimeError("模型本轮未完整返回，已保存之前的工具结果；可继续任务。")
    result = {"items": [item.model_dump(exclude_none=True) for item in response.output],
              "calls": [{"id": item.call_id, "name": item.name, "arguments": item.arguments}
                        for item in response.output if item.type == "function_call"]}
    usage = response.usage
    return attach_usage_payload(result, provider="openai", model=provider.model,
                                usage={"input_tokens": getattr(usage, "input_tokens", 0),
                                       "output_tokens": getattr(usage, "output_tokens", 0)})


async def anthropic_turn(provider, instructions, messages, tools):
    native = []
    for message in messages:
        role = message["role"]
        if role == "assistant":
            native.append({"role": role, "content": message["items"]})
        elif role == "tool":
            block = {"type": "tool_result", "tool_use_id": message["call_id"], "content": message["content"]}
            if native and native[-1]["role"] == "user":
                native[-1]["content"].append(block)
            else:
                native.append({"role": "user", "content": [block]})
        else:
            blocks = [{"type": "text", "text": message["content"]}]
            for img in message.get("images", []):
                header, data = img["data_url"].split(",", 1)
                blocks.extend([{"type": "text", "text": f"Attachment #{img['id']}"},
                               {"type": "image", "source": {"type": "base64",
                                "media_type": header[5:].split(";")[0], "data": data}}])
            native.append({"role": "user", "content": blocks})
    response = await asyncio.to_thread(
        provider.client.messages.create, model=provider.model, system=instructions, messages=native,
        tools=[{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]} for t in tools],
        tool_choice={"type": "any", "disable_parallel_tool_use": True}, max_tokens=7000, timeout=120,
    )
    if response.stop_reason == "max_tokens":
        raise RuntimeError("模型工具调用被截断；已保存之前的工具结果。")
    result = {"items": [item.model_dump(exclude_none=True) for item in response.content],
              "calls": [{"id": item.id, "name": item.name, "arguments": json.dumps(item.input, ensure_ascii=False)}
                        for item in response.content if item.type == "tool_use"]}
    return attach_usage_payload(result, provider="anthropic", model=provider.model,
                                usage={"input_tokens": response.usage.input_tokens,
                                       "output_tokens": response.usage.output_tokens})


async def compatible_turn(provider, instructions, messages, tools):
    """Chat Completions native tools for configured compatible vendor endpoints."""
    native = [{"role": "system", "content": instructions}]
    for message in messages:
        if message["role"] == "assistant":
            native.extend(message["items"])
        elif message["role"] == "tool":
            native.append({"role": "tool", "tool_call_id": message["call_id"], "content": message["content"]})
        else:
            content = [{"type": "text", "text": message["content"]}]
            content.extend({"type": "image_url", "image_url": {"url": i["data_url"]}} for i in message.get("images", []))
            native.append({"role": "user", "content": content if message.get("images") else message["content"]})
    response = await asyncio.to_thread(provider.client.chat.completions.create, model=provider.model,
                                      messages=native, tools=[{"type": "function", "function": t} for t in tools],
                                      tool_choice="required", max_tokens=7000, timeout=120)
    choice = response.choices[0]
    if choice.finish_reason == "length":
        raise RuntimeError("模型工具调用被截断；已保存之前的结果。")
    result = {"items": [choice.message.model_dump(exclude_none=True)],
              "calls": [{"id": c.id, "name": c.function.name, "arguments": c.function.arguments} for c in choice.message.tool_calls or []]}
    return attach_usage_payload(result, provider="openai_compatible", model=provider.model,
                                usage=response.usage.model_dump() if response.usage else {})
