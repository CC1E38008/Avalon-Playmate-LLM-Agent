
"""
阿瓦隆游戏核心逻辑模块
10人局：梅林、派西维尔、忠臣x4、莫甘娜、刺客、莫德雷德、奥伯伦
"""
import random
import time
import uuid
import json
import logging
import threading
from enum import Enum
from typing import Optional

from .llm_client import llm_manager, LLMConfig

logger = logging.getLogger('avalon.game')

# ============================================================
# 常量定义
# ============================================================

ALL_PLAYERS = ['U', 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I']
AI_PLAYERS = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I']
HUMAN_PLAYER = 'U'

ROLE_NAMES = {
    'merlin': '梅林',
    'percival': '派西维尔',
    'loyal': '忠臣',
    'morgana': '莫甘娜',
    'assassin': '刺客',
    'mordred': '莫德雷德',
    'oberon': '奥伯伦',
}

ROLE_TEAM = {
    'merlin': 'good',
    'percival': 'good',
    'loyal': 'good',
    'morgana': 'evil',
    'assassin': 'evil',
    'mordred': 'evil',
    'oberon': 'evil',
}

ROLES_10P = [
    'merlin', 'percival',
    'loyal', 'loyal', 'loyal', 'loyal',
    'morgana', 'assassin', 'mordred', 'oberon',
]

# 任务所需人数 (10人局)
MISSION_SIZES = [3, 4, 4, 5, 5]
# 任务失败所需票数
MISSION_FAILS_NEEDED = [1, 1, 1, 2, 1]

MAX_REJECTIONS = 5


class GamePhase(Enum):
    SETUP = 'setup'
    ROLE_REVEAL = 'role_reveal'       # 角色揭示阶段 (玩家了解自己身份)
    LEADER_PROPOSAL = 'leader_proposal'  # 队长选人
    DISCUSSION = 'discussion'          # 发言阶段
    TEAM_VOTE = 'team_vote'           # 对队伍投票
    MISSION_VOTE = 'mission_vote'     # 任务执行投票
    ASSASSINATION = 'assassination'   # 暗杀阶段
    GAME_OVER = 'game_over'


class Player:
    """玩家"""
    def __init__(self, name: str, is_human: bool = False):
        self.name = name
        self.is_human = is_human
        self.role = None
        self.alive = True
        self.llm: Optional[LLMConfig] = None   # AI 玩家绑定的 LLM
        # 视野信息
        self.known_good = []     # 已知的好人
        self.known_evil = []     # 已知的坏人
        self.known_merlin_candidates = []  # 派西维尔看到的梅林候选人

    @property
    def team(self):
        return ROLE_TEAM.get(self.role, 'unknown')

    @property
    def role_name(self):
        return ROLE_NAMES.get(self.role, '未知')

    def to_dict(self, reveal_all=False):
        d = {
            'name': self.name,
            'is_human': self.is_human,
            'alive': self.alive,
            'team': self.team if (reveal_all or self.is_human) else 'unknown',
        }
        if reveal_all:
            d['role'] = self.role
            d['role_name'] = self.role_name
            d['llm_name'] = self.llm.name if self.llm else 'N/A'
        elif self.is_human:
            d['role'] = self.role
            d['role_name'] = self.role_name
            d['known_good'] = self.known_good
            d['known_evil'] = self.known_evil
            d['known_merlin_candidates'] = self.known_merlin_candidates
        return d


class GameState:
    """游戏状态"""

    def __init__(self, game_id: str):
        self.game_id = game_id
        self.players: dict[str, Player] = {}
        self.phase = GamePhase.SETUP
        self.round_num = 0           # 当前任务轮次 (1-5)
        self.mission_num = 0         # 等同于 round_num
        self.leader_index = 0        # 当前队长在 all_players 中的索引
        self.consecutive_rejections = 0
        self.forced_mission = False    # 当前是否为强制出征任务
        self.mission_results = []    # [(success_count, fail_count, passed_bool), ...]
        self.discussion_order = []   # 本轮发言顺序
        self.current_speaker_idx = 0
        self.proposed_team = []      # 队长提议的队伍
        self.team_votes = {}         # {player_name: 'Y'/'N'}
        self.mission_votes = {}      # {player_name: 'success'/'fail'}
        self.speeches = []           # [(player_name, text, timestamp), ...]
        self.game_log = []           # 游戏事件日志
        self.winner = None           # 'good' / 'evil'
        self.assassin_guess = None   # 刺客猜测的梅林
        self.assassin_correct = None
        self.llm_to_player = {}      # {llm_id: [player_names]}
        self.human_action_needed = None  # 当前需要人类操作的描述
        self.human_action_type = None    # 'speak' / 'vote_team' / 'vote_mission' / 'assassinate'
        self.processing_ai = False
        self.created_at = time.time()
        self.last_activity = time.time()
        self._lock = threading.Lock()

    # ================================================================
    # 游戏初始化
    # ================================================================

    def initialize(self, llm_configs: list[dict]):
        """初始化游戏"""
        # 创建玩家
        for name in ALL_PLAYERS:
            is_human = (name == HUMAN_PLAYER)
            self.players[name] = Player(name, is_human)

        # 随机分配角色
        roles = list(ROLES_10P)
        random.shuffle(roles)
        for name, role in zip(ALL_PLAYERS, roles):
            self.players[name].role = role

        # 随机分配 LLM 给 AI 玩家
        ai_players = [p for p in self.players.values() if not p.is_human]
        llm_list = []
        for cfg in llm_configs:
            llm = llm_manager.add_llm(cfg['name'], cfg['endpoint'], cfg['model'], cfg['api_key'])
            llm_list.append(llm)

        # 打乱 AI 玩家和 LLM 分配
        shuffled_ai = list(ai_players)
        random.shuffle(shuffled_ai)

        for i, player in enumerate(shuffled_ai):
            llm = llm_list[i % len(llm_list)]
            player.llm = llm
            if llm.llm_id not in self.llm_to_player:
                self.llm_to_player[llm.llm_id] = []
            self.llm_to_player[llm.llm_id].append(player.name)

        # 设置视野
        self._setup_vision()

        # 随机初始队长
        self.leader_index = random.randint(0, 9)

        self.phase = GamePhase.ROLE_REVEAL
        self._add_log("游戏开始！角色已分配。")
        self.last_activity = time.time()

    def _setup_vision(self):
        """设置每个角色的视野"""
        evil_players = [p for p in self.players.values() if p.team == 'evil']
        good_players = [p for p in self.players.values() if p.team == 'good']

        for player in self.players.values():
            role = player.role

            if role == 'merlin':
                # 梅林: 知道所有坏人，除了莫德雷德
                for ep in evil_players:
                    if ep.role != 'mordred':
                        player.known_evil.append(ep.name)
                remaining = [p.name for p in self.players.values()
                           if p.name not in player.known_evil and p.name != player.name]
                player.known_good = [n for n in remaining if self.players[n].team == 'good']

            elif role == 'percival':
                # 派西维尔: 知道梅林和莫甘娜 (但不知道谁是谁)
                merlin_name = None
                morgana_name = None
                for p in self.players.values():
                    if p.role == 'merlin':
                        merlin_name = p.name
                    elif p.role == 'morgana':
                        morgana_name = p.name
                player.known_merlin_candidates = [merlin_name, morgana_name]
                # 其他所有玩家标记为好人或未知
                for p in self.players.values():
                    if p.name in player.known_merlin_candidates or p.name == player.name:
                        continue
                    if p.team == 'evil' and p.role not in ('merlin', 'morgana'):
                        pass  # 未知
                    elif p.team == 'good':
                        player.known_good.append(p.name)

            elif role == 'morgana':
                # 莫甘娜: 知道刺客、莫德雷德 (不知道奥伯伦)
                for ep in evil_players:
                    if ep.role != 'oberon' and ep.name != player.name:
                        player.known_evil.append(ep.name)

            elif role == 'assassin':
                # 刺客: 知道莫甘娜、莫德雷德 (不知道奥伯伦)
                for ep in evil_players:
                    if ep.role != 'oberon' and ep.name != player.name:
                        player.known_evil.append(ep.name)

            elif role == 'mordred':
                # 莫德雷德: 知道莫甘娜、刺客 (不知道奥伯伦)
                for ep in evil_players:
                    if ep.role != 'oberon' and ep.name != player.name:
                        player.known_evil.append(ep.name)

            elif role == 'oberon':
                # 奥伯伦: 不知道任何人，其他坏人也不知道奥伯伦
                pass

            elif role == 'loyal':
                # 忠臣: 不知道任何人
                pass

    # ================================================================
    # 游戏流程
    # ================================================================

    def get_human_player(self) -> Player:
        return self.players[HUMAN_PLAYER]

    def get_alive_players(self) -> list[Player]:
        return [p for p in self.players.values() if p.alive]

    def get_current_leader(self) -> Player:
        alive = [p.name for p in self.get_alive_players()]
        ordered = [n for n in ALL_PLAYERS if n in alive]
        return self.players[ordered[self.leader_index % len(ordered)]]

    def _add_log(self, msg: str):
        self.game_log.append({
            'time': time.strftime('%H:%M:%S'),
            'message': msg,
        })
        self.last_activity = time.time()

    def _add_speech(self, player_name: str, text: str):
        self.speeches.append({
            'player': player_name,
            'text': text,
            'time': time.strftime('%H:%M:%S'),
        })
        self._add_log(f"玩家 {player_name} 发言: {text[:100]}{'...' if len(text) > 100 else ''}")

    def to_dict(self):
        """转换为前端可用的字典"""
        alive_names = [p.name for p in self.get_alive_players()]
        return {
            'game_id': self.game_id,
            'phase': self.phase.value,
            'round_num': self.round_num,
            'mission_num': self.mission_num,
            'mission_sizes': MISSION_SIZES,
            'current_mission_size': MISSION_SIZES[self.mission_num - 1] if self.mission_num > 0 else 0,
            'leader': self.get_current_leader().name if self.mission_num > 0 else None,
            'proposed_team': self.proposed_team,
            'team_votes': self.team_votes,
            'mission_votes': self.mission_votes,
            'mission_results': self.mission_results,
            'consecutive_rejections': self.consecutive_rejections,
            'forced_mission': self.forced_mission,
            'max_rejections': MAX_REJECTIONS,
            'speeches': self.speeches[-50:],  # 只发送最近50条发言
            'game_log': self.game_log[-30:],
            'discussion_order': self.discussion_order,
            'current_speaker': self.discussion_order[self.current_speaker_idx] if self.current_speaker_idx < len(self.discussion_order) else None,
            'human_player': self.get_human_player().to_dict(),
            'all_players': [p.to_dict(reveal_all=(self.phase == GamePhase.GAME_OVER)) for p in self.players.values()],
            'alive_players': alive_names,
            'winner': self.winner,
            'assassin_guess': self.assassin_guess,
            'assassin_correct': self.assassin_correct,
            'human_action_needed': self.human_action_needed,
            'human_action_type': self.human_action_type,
            'processing_ai': self.processing_ai,
        }

    # ================================================================
    # 主要游戏循环 - 推进到下一个需要人类操作的点
    # ================================================================

    def advance(self):
        """
        推进游戏状态，直到需要人类操作或游戏结束。
        在人类提交操作后调用此方法。
        """
        with self._lock:
            self._advance_internal()

    def _advance_internal(self):
        """内部推进逻辑（已上锁）"""
        max_iterations = 50
        for _ in range(max_iterations):
            if self.phase == GamePhase.GAME_OVER:
                self.human_action_needed = None
                self.human_action_type = None
                return

            if self.phase == GamePhase.ROLE_REVEAL:
                self._start_first_mission()
                continue

            if self.phase == GamePhase.LEADER_PROPOSAL:
                # 检查是否是当前人类玩家当队长
                leader = self.get_current_leader()
                if leader.is_human:
                    self.human_action_needed = f"你是队长，请选择 {MISSION_SIZES[self.mission_num - 1]} 名玩家执行任务第 {self.mission_num} 轮"
                    self.human_action_type = 'propose_team'
                    return
                else:
                    # AI 队长自动选人
                    self._ai_propose_team(leader)
                    continue

            if self.phase == GamePhase.DISCUSSION:
                if self.current_speaker_idx >= len(self.discussion_order):
                    # 发言结束，进入投票
                    self.phase = GamePhase.TEAM_VOTE
                    self.team_votes = {}
                    self._add_log("发言结束，开始对队伍进行投票。")
                    continue

                speaker_name = self.discussion_order[self.current_speaker_idx]
                speaker = self.players[speaker_name]

                if speaker.is_human:
                    self.human_action_needed = f"请发言 (你是 {speaker_name}, 角色: {speaker.role_name})"
                    self.human_action_type = 'speak'
                    return
                else:
                    # AI 发言
                    self._ai_speak(speaker)
                    self.current_speaker_idx += 1
                    continue

            if self.phase == GamePhase.TEAM_VOTE:
                # 收集每个存活玩家的投票
                alive = [p.name for p in self.get_alive_players()]
                needs_vote = [n for n in alive if n not in self.team_votes]

                if not needs_vote:
                    # 所有人投票完毕
                    self._process_team_vote_result()
                    continue

                voter_name = needs_vote[0]
                voter = self.players[voter_name]

                if voter.is_human:
                    self.human_action_needed = f"你对队伍 {', '.join(self.proposed_team)} 投赞成(Y)还是反对(N)?"
                    self.human_action_type = 'vote_team'
                    return
                else:
                    self._ai_vote_team(voter)
                    continue

            if self.phase == GamePhase.MISSION_VOTE:
                mission_members = [n for n in self.proposed_team]
                needs_vote = [n for n in mission_members if n not in self.mission_votes]

                if not needs_vote:
                    self._process_mission_result()
                    continue

                voter_name = needs_vote[0]
                voter = self.players[voter_name]

                if voter.is_human:
                    if self.forced_mission:
                        self.human_action_needed = f"⚠️ 强制出征！你在任务队伍中。若任务失败则坏人直接获胜。请投票 (success=成功 / fail=失败)"
                    else:
                        self.human_action_needed = f"你在任务队伍中！请投任务票 (success=任务成功 / fail=任务失败)"
                    self.human_action_type = 'vote_mission'
                    return
                else:
                    self._ai_vote_mission(voter)
                    continue

            if self.phase == GamePhase.ASSASSINATION:
                assassin = self._find_role_player('assassin')
                if assassin is None:
                    self.winner = 'good'
                    self.phase = GamePhase.GAME_OVER
                    self._add_log("未找到刺客，好人阵营获胜！")
                    continue

                if assassin.is_human:
                    self.human_action_needed = "你是刺客！请猜测谁是梅林。"
                    self.human_action_type = 'assassinate'
                    return
                else:
                    self._ai_assassinate(assassin)
                    continue

            # 如果循环中没有触发任何continue，退出
            break

        # 最终检查
        if self.phase == GamePhase.GAME_OVER:
            self.human_action_needed = None
            self.human_action_type = None

    # ================================================================
    # 人类操作入口
    # ================================================================

    def human_action(self, action_type: str, data: dict):
        """处理人类玩家的操作"""
        with self._lock:
            if action_type == 'init':
                # 初始化，推进游戏到第一个人类操作点
                self._advance_internal()

            elif action_type == 'speak':
                text = data.get('text', '')
                self._add_speech(HUMAN_PLAYER, text)
                self.current_speaker_idx += 1
                self._advance_internal()

            elif action_type == 'vote_team':
                vote = data.get('vote', 'N')
                self.team_votes[HUMAN_PLAYER] = vote
                self._advance_internal()

            elif action_type == 'vote_mission':
                vote = data.get('vote', 'success')
                self.mission_votes[HUMAN_PLAYER] = vote
                self._advance_internal()

            elif action_type == 'propose_team':
                team = data.get('team', [])
                self._human_propose_team(team)
                self._advance_internal()

            elif action_type == 'assassinate':
                # 仅刺客本人可执行暗杀
                if self.get_human_player().role != 'assassin':
                    return
                guess = data.get('guess', '')
                self.assassin_guess = guess
                self._process_assassination()
                self._advance_internal()

    def _human_propose_team(self, team: list[str]):
        """人类队长选人"""
        size = MISSION_SIZES[self.mission_num - 1]
        if len(team) != size:
            # 自动截取或补全
            alive = [p.name for p in self.get_alive_players()]
            team = team[:size]
            while len(team) < size:
                for n in alive:
                    if n not in team:
                        team.append(n)
                        break
        self.proposed_team = team[:size]
        self._add_log(f"队长 {HUMAN_PLAYER} 提议任务队伍: {', '.join(self.proposed_team)}")
        self._start_discussion()

    # ================================================================
    # 阶段转换
    # ================================================================

    def _start_first_mission(self):
        self.mission_num = 1
        self.round_num = 1
        self.consecutive_rejections = 0
        self.mission_results = []
        self.phase = GamePhase.LEADER_PROPOSAL
        leader = self.get_current_leader()
        self._add_log(f"第 {self.mission_num} 轮任务开始。队长: {leader.name}")

    def _start_discussion(self):
        self.phase = GamePhase.DISCUSSION
        alive = [p.name for p in self.get_alive_players()]
        # 随机发言顺序（从队长左手边开始，即下一个玩家）
        ordered_all = [n for n in ALL_PLAYERS if n in alive]
        leader_idx = ordered_all.index(self.get_current_leader().name)
        self.discussion_order = ordered_all[leader_idx:] + ordered_all[:leader_idx]
        self.current_speaker_idx = 0
        self.speeches = []
        self._add_log(f"发言顺序: {' → '.join(self.discussion_order)}")

    def _process_team_vote_result(self):
        """处理队伍投票结果"""
        yes_count = sum(1 for v in self.team_votes.values() if v == 'Y')
        no_count = sum(1 for v in self.team_votes.values() if v == 'N')

        vote_detail = ', '.join(f"{n}:{'✓' if v == 'Y' else '✗'}" for n, v in sorted(self.team_votes.items()))
        self._add_log(f"队伍投票: {vote_detail}")
        self._add_log(f"结果: {yes_count} 赞成 / {no_count} 反对")

        if yes_count > no_count:
            # 投票通过
            self.consecutive_rejections = 0
            self._add_log("队伍投票通过！开始执行任务。")
            self.phase = GamePhase.MISSION_VOTE
            self.mission_votes = {}
        else:
            # 投票不通过
            self.consecutive_rejections += 1
            self._add_log(f"队伍投票未通过！连续拒绝: {self.consecutive_rejections}/{MAX_REJECTIONS}")

            if self.consecutive_rejections >= MAX_REJECTIONS:
                # 5次否决 → 强制出征（直接进入任务执行，不再投票）
                self.forced_mission = True
                self.phase = GamePhase.MISSION_VOTE
                self.mission_votes = {}
                self._add_log(f"连续{MAX_REJECTIONS}次队伍被否决！队伍强制出征: {', '.join(self.proposed_team)}")
                self._add_log("⚠️ 如果此次强制任务失败，坏人阵营直接获胜！")
            else:
                # 下一个队长
                self.leader_index = (self.leader_index + 1) % 10
                leader = self.get_current_leader()
                self._add_log(f"新队长: {leader.name}")
                self.phase = GamePhase.LEADER_PROPOSAL

    def _process_mission_result(self):
        """处理任务执行结果"""
        fail_count = sum(1 for v in self.mission_votes.values() if v == 'fail')
        success_count = len(self.mission_votes) - fail_count
        fails_needed = MISSION_FAILS_NEEDED[self.mission_num - 1]
        passed = fail_count < fails_needed

        self.mission_results.append({
            'mission': self.mission_num,
            'success': success_count,
            'fail': fail_count,
            'passed': passed,
            'team': list(self.proposed_team),
        })

        status = '✓ 任务成功' if passed else '✗ 任务失败'
        self._add_log(f"第 {self.mission_num} 轮任务结果: {status} (成功:{success_count} 失败:{fail_count})")

        # 检查胜利条件
        good_wins = sum(1 for r in self.mission_results if r['passed'])
        evil_wins = sum(1 for r in self.mission_results if not r['passed'])

        # 强制出征任务失败 → 坏人直接获胜
        if self.forced_mission and not passed:
            self.winner = 'evil'
            self.phase = GamePhase.GAME_OVER
            self._add_log("强制出征任务失败！坏人阵营获胜！")
            return

        # 强制出征任务成功 → 重置标记，继续游戏
        if self.forced_mission and passed:
            self._add_log("强制出征任务成功！游戏继续。")
        self.forced_mission = False

        if good_wins >= 3:
            # 好人赢得3轮，进入暗杀阶段
            self.phase = GamePhase.ASSASSINATION
            self._add_log("好人阵营赢得3轮任务！进入暗杀阶段。")
        elif evil_wins >= 3:
            self.winner = 'evil'
            self.phase = GamePhase.GAME_OVER
            self._add_log("坏人阵营赢得3轮任务，坏人获胜！")
        else:
            # 下一轮
            self.mission_num += 1
            self.round_num += 1
            self.consecutive_rejections = 0
            self.leader_index = (self.leader_index + 1) % 10
            leader = self.get_current_leader()
            self._add_log(f"第 {self.mission_num} 轮任务开始。队长: {leader.name}")
            self.phase = GamePhase.LEADER_PROPOSAL

    def _process_assassination(self):
        """处理暗杀结果"""
        merlin = self._find_role_player('merlin')
        self.assassin_correct = (self.assassin_guess == merlin.name)

        if self.assassin_correct:
            self.winner = 'evil'
            self._add_log(f"刺客猜中梅林({merlin.name})！坏人阵营获胜！")
        else:
            self.winner = 'good'
            self._add_log(f"刺客猜错({self.assassin_guess}不是梅林，梅林是{merlin.name})！好人阵营获胜！")

        self.phase = GamePhase.GAME_OVER

    # ================================================================
    # AI 行为
    # ================================================================

    def _build_context_for_ai(self, player: Player) -> str:
        """为 AI 玩家构建游戏上下文"""
        parts = []
        parts.append(f"=== 阿瓦隆游戏 - 第 {self.mission_num} 轮任务 ===")
        parts.append(f"你是玩家 {player.name}。")
        parts.append("")

        # 当前存活的玩家
        alive = [p.name for p in self.get_alive_players()]
        parts.append(f"当前存活玩家 ({len(alive)}人): {', '.join(alive)}")
        parts.append(f"总玩家数: 10 (6好人 vs 4坏人)")
        parts.append("")

        # 已完成的投票记录
        if self.mission_results:
            parts.append("--- 已执行的任务 ---")
            for r in self.mission_results:
                status = '成功✓' if r['passed'] else '失败✗'
                parts.append(f"第{r['mission']}轮: {status} (队伍: {', '.join(r['team'])}) 成功{r['success']}票/失败{r['fail']}票")
            parts.append("")
            good_wins = sum(1 for r in self.mission_results if r['passed'])
            evil_wins = sum(1 for r in self.mission_results if not r['passed'])
            parts.append(f"当前比分: 好人 {good_wins} - {evil_wins} 坏人")
            parts.append("")

        # 最近发言
        if hasattr(self, 'speeches') and self.speeches:
            parts.append("--- 本轮发言记录 ---")
            for s in self.speeches:
                parts.append(f"玩家{s['player']}: {s['text']}")
            parts.append("")

        # 本轮提议
        if self.proposed_team:
            parts.append(f"当前提议的队伍: {', '.join(self.proposed_team)}")
            parts.append("")

        # 队伍投票结果
        if self.team_votes:
            parts.append("--- 队伍投票 ---")
            for n, v in sorted(self.team_votes.items()):
                parts.append(f"{n}: {'赞成' if v == 'Y' else '反对'}")
            parts.append("")

        parts.append(f"当前队长: {self.get_current_leader().name}")
        parts.append(f"讨论顺序: {' → '.join(self.discussion_order)}")
        parts.append("")

        return "\n".join(parts)

    def _get_system_prompt(self, player: Player) -> str:
        """为 AI 玩家生成系统提示词"""
        role = player.role
        role_name = player.role_name
        team = '好人(亚瑟的忠臣)' if player.team == 'good' else '坏人(莫德雷德的爪牙)'

        prompt = f"""你正在玩阿瓦隆桌游，你是玩家 {player.name}。

你的角色: {role_name} ({team})
你的目标: 帮助你的阵营赢得游戏！

游戏规则:
- 10人局: 6好人(梅林、派西维尔、4忠臣) vs 4坏人(莫甘娜、刺客、莫德雷德、奥伯伦)
- 5轮任务，好人赢3轮触发暗杀阶段，坏人赢3轮直接获胜
- 每轮队长选人做任务，全体投票决定是否通过队伍
- 连续5次队伍被拒绝则坏人直接获胜
- 第4轮任务(5人队)需要2张失败票才算失败，其他轮只需1张

你的角色说明:
"""

        if role == 'merlin':
            prompt += f"""- 你是梅林，你知道所有坏人(除了莫德雷德)
- 已知坏人: {', '.join(player.known_evil) if player.known_evil else '无'}
- 你必须隐藏身份，不能太明显，否则游戏结束后会被刺客暗杀
- 你可以引导讨论，但不要太直接指认坏人"""
        elif role == 'percival':
            prompt += f"""- 你是派西维尔，你知道梅林和莫甘娜是谁(但不知道分别是谁)
- 梅林/莫甘娜候选人: {', '.join(player.known_merlin_candidates)}
- 你需要找出真正的梅林并支持他，同时小心莫甘娜的欺骗"""
        elif role == 'loyal':
            prompt += """- 你是忠臣，你不知道任何人的身份
- 你需要通过发言和投票来找出坏人
- 注意观察谁在试图破坏任务"""
        elif role == 'morgana':
            prompt += f"""- 你是莫甘娜，派西维尔会把你和梅林混淆
- 已知队友: {', '.join(player.known_evil)}
- 你需要伪装成梅林来迷惑派西维尔
- 在任务中适时投失败票，但不要太明显"""
        elif role == 'assassin':
            prompt += f"""- 你是刺客，游戏结束后如果好人赢3轮，你可以暗杀梅林
- 已知队友: {', '.join(player.known_evil)}
- 观察谁可能是梅林，为暗杀做准备
- 在任务中适时投失败票"""
        elif role == 'mordred':
            prompt += f"""- 你是莫德雷德，梅林看不到你
- 已知队友: {', '.join(player.known_evil)}
- 你可以安全地伪装成好人
- 在任务中适时投失败票"""
        elif role == 'oberon':
            prompt += """- 你是奥伯伦，你不知道其他坏人，其他坏人也不知道你
- 你是孤立的坏人，需要自己判断局势
- 尽量破坏任务，但要小心不被发现"""

        prompt += f"""

发言要求:
- 用自然的中文发言，像真人玩家一样
- 可以伪装、演戏、误导，但必须以帮助自己阵营获胜为目的
- 发言不要太长，2-5句话即可
- 可以评论其他人的发言、提出怀疑、表达观点
"""
        return prompt

    def _call_llm_for_player(self, player: Player, user_prompt: str, temperature: float = 0.8, max_tokens: int = 512) -> str:
        """调用 LLM 为玩家生成响应"""
        if player.llm is None:
            return "[无LLM]"
        system = self._get_system_prompt(player)
        full_user = self._build_context_for_ai(player) + "\n" + user_prompt
        return llm_manager.call_llm(player.llm, system, full_user, temperature, max_tokens)

    def _ai_propose_team(self, leader: Player):
        """AI 队长选人"""
        self.processing_ai = True
        size = MISSION_SIZES[self.mission_num - 1]
        alive = [p.name for p in self.get_alive_players()]

        prompt = f"""你是本轮队长，请选择 {size} 名玩家执行第 {self.mission_num} 轮任务。

存活玩家: {', '.join(alive)}
任务需要人数: {size}

请只回复你选择的队伍(用逗号分隔玩家名，如: A,B,C,D)，不要加其他内容。"""
        resp = self._call_llm_for_player(leader, prompt, temperature=0.5, max_tokens=100)

        # 解析队伍
        team = []
        for ch in resp:
            if ch in AI_PLAYERS + ['U']:
                if ch not in team and ch in alive:
                    team.append(ch)

        # 如果解析失败或不够，自动补齐
        if len(team) < size:
            for n in alive:
                if n not in team:
                    team.append(n)
                if len(team) >= size:
                    break
        team = team[:size]

        self.proposed_team = team
        self._add_log(f"队长 {leader.name} 提议任务队伍: {', '.join(team)}")
        self._start_discussion()
        self.processing_ai = False

    def _ai_speak(self, player: Player):
        """AI 发言"""
        self.processing_ai = True
        prompt = f"""现在轮到你发言了。你是玩家 {player.name}。

请发表你对当前局势的看法，帮助你的阵营赢得游戏。
记住你的角色设定和视野信息。
发言用中文，2-5句话即可，像真人玩家一样自然。

请直接回复你的发言内容，不要加任何前缀。"""
        resp = self._call_llm_for_player(player, prompt, temperature=0.9, max_tokens=512)
        self._add_speech(player.name, resp)
        self.processing_ai = False

    def _ai_vote_team(self, player: Player):
        """AI 投票"""
        self.processing_ai = True
        prompt = f"""现在对队伍 [{', '.join(self.proposed_team)}] 进行投票。

请只回复一个字母: Y (赞成) 或 N (反对)。
不要添加任何其他内容。"""
        resp = self._call_llm_for_player(player, prompt, temperature=0.3, max_tokens=10)
        vote = 'Y' if 'Y' in resp.upper() else 'N'
        self.team_votes[player.name] = vote
        self.processing_ai = False

    def _ai_vote_mission(self, player: Player):
        """AI 任务投票"""
        self.processing_ai = True
        prompt = f"""你在任务队伍中！请投票。

好人只能投"成功"。坏人可以投"成功"或"失败"。

请只回复一个词: success (成功) 或 fail (失败)。
不要添加任何其他内容。"""
        resp = self._call_llm_for_player(player, prompt, temperature=0.5, max_tokens=10)
        vote = 'fail' if 'fail' in resp.lower() else 'success'
        self.mission_votes[player.name] = vote
        self.processing_ai = False

    def _ai_assassinate(self, assassin: Player):
        """AI 暗杀猜测"""
        self.processing_ai = True
        alive = [p.name for p in self.get_alive_players() if p.name != assassin.name]
        prompt = f"""你是刺客！好人阵营赢得了3轮任务，现在你要猜测谁是梅林。

如果你猜对了，坏人阵营翻盘获胜。
存活玩家: {', '.join(alive)}

请只回复一个玩家的名字(A-I或U)，这是你猜测的梅林。
不要添加任何其他内容。"""
        resp = self._call_llm_for_player(assassin, prompt, temperature=0.5, max_tokens=20)
        guess = resp.strip().upper()
        if guess not in ALL_PLAYERS:
            guess = random.choice([n for n in alive])
        self.assassin_guess = guess
        self._process_assassination()
        self.processing_ai = False

    # ================================================================
    # 辅助方法
    # ================================================================

    def _find_role_player(self, role: str) -> Optional[Player]:
        for p in self.players.values():
            if p.role == role:
                return p
        return None

    def get_game_result(self) -> dict:
        """获取游戏结果数据"""
        result = {
            'game_id': self.game_id,
            'winner': self.winner,
            'winner_team': '好人阵营' if self.winner == 'good' else '坏人阵营',
            'mission_results': self.mission_results,
            'assassin_guess': self.assassin_guess,
            'assassin_correct': self.assassin_correct,
            'players': [],
            'llm_stats': {},
        }

        for p in self.players.values():
            result['players'].append({
                'name': p.name,
                'role': p.role,
                'role_name': p.role_name,
                'team': p.team,
                'is_human': p.is_human,
                'llm_name': p.llm.name if p.llm else '人类',
                'llm_model': p.llm.model if p.llm else 'N/A',
            })

        # 计算每个 LLM 的统计
        for llm in llm_manager.llms:
            players_for_llm = self.llm_to_player.get(llm.llm_id, [])
            wins = 0
            total = len(players_for_llm)
            for pname in players_for_llm:
                if self.players[pname].team == self.winner:
                    wins += 1
            result['llm_stats'][llm.llm_id] = {
                'name': llm.name,
                'model': llm.model,
                'players': players_for_llm,
                'total_players': total,
                'wins': wins,
                'win_rate': wins / total if total > 0 else 0,
            }

        return result


# ================================================================
# 全局游戏存储 (in-memory)
# ================================================================

games: dict[str, GameState] = {}
games_lock = threading.Lock()


def create_game(llm_configs: list[dict]) -> GameState:
    game_id = uuid.uuid4().hex[:12]
    game = GameState(game_id)
    game.initialize(llm_configs)
    with games_lock:
        games[game_id] = game
    return game


def get_game(game_id: str) -> Optional[GameState]:
    with games_lock:
        return games.get(game_id)


def cleanup_old_games(max_age=86400):
    """清理旧游戏"""
    now = time.time()
    with games_lock:
        to_remove = [gid for gid, g in games.items() if now - g.last_activity > max_age]
        for gid in to_remove:
            del games[gid]
