
"""
阿瓦隆游戏 Django 视图
"""
import json
import threading
import logging
from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods

from .game_state import create_game, get_game, GamePhase, MISSION_SIZES, ALL_PLAYERS
from .llm_client import llm_manager

logger = logging.getLogger('avalon.views')

# 游戏结果日志文件
RESULT_LOG_FILE = 'game_results_of_LLM.log'


def _log_game_result(result: dict):
    """将游戏结果写入日志"""
    import os
    log_entry = {
        'game_id': result['game_id'],
        'winner': result['winner'],
        'winner_team': result['winner_team'],
        'players': result['players'],
        'llm_stats': result['llm_stats'],
    }
    with open(RESULT_LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
    logger.info(f"Game result logged to {RESULT_LOG_FILE}")


# ================================================================
# 页面视图
# ================================================================

def index(request):
    """首页 - 设置页面"""
    return render(request, 'game/index.html')


def game_page(request, game_id):
    """游戏主页面"""
    game = get_game(game_id)
    if game is None:
        return render(request, 'game/index.html', {'error': '游戏不存在或已过期'})
    return render(request, 'game/game.html', {
        'game_id': game_id,
    })


def result_page(request, game_id):
    """结算页面"""
    game = get_game(game_id)
    if game is None:
        return render(request, 'game/index.html', {'error': '游戏不存在或已过期'})

    result = game.get_game_result()
    _log_game_result(result)

    return render(request, 'game/result.html', {
        'game_id': game_id,
        'result': json.dumps(result, ensure_ascii=False),
    })


# ================================================================
# API 视图
# ================================================================

@require_http_methods(["POST"])
def setup_game(request):
    """初始化游戏"""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': '无效的 JSON'}, status=400)

    llm_count = data.get('llm_count', 1)
    if not isinstance(llm_count, int) or llm_count < 1 or llm_count > 9:
        return JsonResponse({'error': 'LLM 数量必须在 1-9 之间'}, status=400)

    llm_configs = data.get('llm_configs', [])
    if len(llm_configs) != llm_count:
        return JsonResponse({'error': f'需要 {llm_count} 个 LLM 配置，收到了 {len(llm_configs)} 个'}, status=400)

    # 清除之前的 LLM 管理器状态
    llm_manager.llms.clear()

    # 创建游戏
    game = create_game(llm_configs)

    # 检查所有 LLM 连接
    def check_connections():
        llm_manager.check_all_connections()

    thread = threading.Thread(target=check_connections, daemon=True)
    thread.start()

    return JsonResponse({
        'game_id': game.game_id,
        'message': '游戏已创建',
    })


@require_http_methods(["GET"])
def game_state_api(request, game_id):
    """获取游戏状态"""
    game = get_game(game_id)
    if game is None:
        return JsonResponse({'error': '游戏不存在'}, status=404)

    state = game.to_dict()
    state['llm_status'] = llm_manager.get_status_list()
    return JsonResponse(state)


@require_http_methods(["POST"])
def game_action(request, game_id):
    """人类玩家操作"""
    game = get_game(game_id)
    if game is None:
        return JsonResponse({'error': '游戏不存在'}, status=404)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': '无效的 JSON'}, status=400)

    action_type = data.get('action_type', '')
    action_data = data.get('data', {})

    game.human_action(action_type, action_data)

    state = game.to_dict()
    state['llm_status'] = llm_manager.get_status_list()
    return JsonResponse(state)


@require_http_methods(["GET"])
def game_result_api(request, game_id):
    """获取游戏结果"""
    game = get_game(game_id)
    if game is None:
        return JsonResponse({'error': '游戏不存在'}, status=404)

    result = game.get_game_result()
    _log_game_result(result)
    result['llm_status'] = llm_manager.get_status_list()
    return JsonResponse(result)
