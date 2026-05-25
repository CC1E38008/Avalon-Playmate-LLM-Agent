"""
LLM 客户端模块 - 支持多个大模型 API 调用
支持 OpenAI 兼容接口 (OpenAI / DeepSeek / Qwen / 等)
"""
import json
import time
import logging
import threading
import urllib.request
import urllib.error

logger = logging.getLogger('avalon.llm')


class LLMConfig:
    """单个 LLM 配置"""
    def __init__(self, llm_id, name, endpoint, model, api_key):
        self.llm_id = llm_id
        self.name = name
        self.endpoint = endpoint.rstrip('/')
        self.model = model
        self.api_key = api_key
        self.status = 'unknown'       # unknown / online / error
        self.status_message = ''
        self.last_check = None

    def to_dict(self):
        return {
            'llm_id': self.llm_id,
            'name': self.name,
            'model': self.model,
            'status': self.status,
            'status_message': self.status_message,
        }


class LLMManager:
    """管理多个 LLM 客户端"""

    def __init__(self):
        self.llms: list[LLMConfig] = []
        self._lock = threading.Lock()

    def add_llm(self, name, endpoint, model, api_key):
        llm = LLMConfig(len(self.llms), name, endpoint, model, api_key)
        self.llms.append(llm)
        return llm

    def check_all_connections(self):
        """并发检查所有 LLM 连接状态"""
        threads = []
        for llm in self.llms:
            t = threading.Thread(target=self._check_one, args=(llm,), daemon=True)
            t.start()
            threads.append(t)
        for t in threads:
            t.join(timeout=15)

    def _check_one(self, llm: LLMConfig):
        """检查单个 LLM 连接"""
        try:
            llm.status = 'checking'
            llm.status_message = '检测中...'

            # 发送一个简单的 ping 请求
            url = f"{llm.endpoint}/chat/completions"
            data = json.dumps({
                "model": llm.model,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 1,
            }).encode('utf-8')

            req = urllib.request.Request(url, data=data, method='POST')
            req.add_header('Content-Type', 'application/json')
            req.add_header('Authorization', f'Bearer {llm.api_key}')

            start = time.time()
            resp = urllib.request.urlopen(req, timeout=15)
            elapsed = time.time() - start

            if resp.status == 200:
                llm.status = 'online'
                llm.status_message = f'✓ 在线 ({elapsed:.1f}s)'
            else:
                llm.status = 'error'
                llm.status_message = f'✗ HTTP {resp.status}'

        except urllib.error.HTTPError as e:
            llm.status = 'error'
            body = ''
            try:
                body = e.read().decode('utf-8', errors='replace')[:200]
            except Exception:
                pass
            llm.status_message = f'✗ HTTP {e.code}: {body}'
        except urllib.error.URLError as e:
            llm.status = 'error'
            llm.status_message = f'✗ 连接失败: {str(e.reason)[:80]}'
        except Exception as e:
            llm.status = 'error'
            llm.status_message = f'✗ {str(e)[:80]}'

    def call_llm(self, llm: LLMConfig, system_prompt: str, user_prompt: str,
                 temperature: float = 0.8, max_tokens: int = 1024) -> str:
        """
        调用指定 LLM
        返回文本响应，出错时返回 "[错误: ...]"
        """
        try:
            url = f"{llm.endpoint}/chat/completions"
            data = json.dumps({
                "model": llm.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
            }).encode('utf-8')

            req = urllib.request.Request(url, data=data, method='POST')
            req.add_header('Content-Type', 'application/json')
            req.add_header('Authorization', f'Bearer {llm.api_key}')

            resp = urllib.request.urlopen(req, timeout=120)
            body = resp.read().decode('utf-8')

            result = json.loads(body)
            content = result['choices'][0]['message']['content']
            return content.strip()

        except urllib.error.HTTPError as e:
            body = ''
            try:
                body = e.read().decode('utf-8', errors='replace')[:300]
            except Exception:
                pass
            logger.error(f"LLM[{llm.name}] HTTP {e.code}: {body}")
            return f"[错误: HTTP {e.code} - {body}]"
        except urllib.error.URLError as e:
            logger.error(f"LLM[{llm.name}] 连接失败: {e.reason}")
            return f"[错误: 连接失败 - {e.reason}]"
        except json.JSONDecodeError as e:
            logger.error(f"LLM[{llm.name}] JSON 解析失败")
            return f"[错误: API 返回无效 JSON]"
        except KeyError:
            logger.error(f"LLM[{llm.name}] 响应格式异常")
            return f"[错误: 响应格式异常]"
        except Exception as e:
            logger.error(f"LLM[{llm.name}] 未知错误: {e}")
            return f"[错误: {str(e)[:100]}]"

    def get_status_list(self):
        return [llm.to_dict() for llm in self.llms]

    def get_online_count(self):
        return sum(1 for llm in self.llms if llm.status == 'online')

    def __len__(self):
        return len(self.llms)


# 全局 LLM 管理器
llm_manager = LLMManager()
