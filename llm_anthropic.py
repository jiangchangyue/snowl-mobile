# test_anthropic_local.py

import anthropic
import time
import json

# --- 配置 ---
# 请将这些值替换为你实际的本地服务信息
MODEL_NAME = "qwen3.6-plus"  # 你本地服务中模型的名称
API_KEY = "sk-e14e66c5cc584db3a6cd32a58d9905bd"  # 你本地服务的 API Key
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1" # 你本地服务的 base_url

# --- 创建客户端 ---
# 使用 Anthropic 客户端，并指定本地服务的 base_url 和 api_key
client = anthropic.Anthropic(
    base_url=BASE_URL,
    api_key=API_KEY,
    # timeout=60, # 可选：设置请求超时时间
)

def chat_anthropic(system_prompt, user_prompt):
    """
    使用 Anthropic 客户端向本地模型发送请求。
    """
    try:
        message = client.messages.create(
            model=MODEL_NAME,
            max_tokens=1024, # Anthropic API 必须指定 max_tokens
            temperature=0.7,
            system=system_prompt, # Anthropic API 中 system prompt 是单独的字段
            messages=[
                {
                    "role": "user",
                    "content": user_prompt,
                }
            ]
        )
        
        # Anthropic 的响应结构略有不同
        resp = message.content[0].text # 获取第一个 content block 的文本
        return resp

    except anthropic.APIConnectionError as e:
        print("服务器连接失败:", e.__cause__)
        return None
    except anthropic.RateLimitError:
        print("达到速率限制，请稍后重试。")
        return None
    except anthropic.AuthenticationError:
        print("认证失败，检查 API Key。")
        return None
    except anthropic.BadRequestError as e:
        print("请求格式错误:", e)
        return None
    except Exception as e:
        print(f"发生未知错误: {e}")
        return None

# --- 测试 ---
if __name__ == "__main__":
    system_prompt = "You are a helpful assistant."
    user_prompt = "你是什么模型？"
    
    print(f"正在向模型 {MODEL_NAME} 发送请求...")
    print(f"System Prompt: {system_prompt}")
    print(f"User Prompt: {user_prompt}")
    print("-" * 20)

    response = chat_anthropic(system_prompt, user_prompt)

    if response:
        print("模型响应:")
        print(response)
    else:
        print("请求失败，无法获取响应。")

    print("-" * 20)
    print("测试结束。")
