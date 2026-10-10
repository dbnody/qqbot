"""轮盘赌和多人 21 点的内存游戏服务。

游戏状态按群号隔离。它们是纯娱乐功能，不涉及真实货币、积分或充值。
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field


def solo_roulette() -> str:
    """单人轮盘赌。"""
    if random.randint(1, 6) == 1:
        return "咔哒……砰！你中了空包弹（游戏效果），本轮结束。"
    return "咔哒……安全！今天的运气不错。"


@dataclass
class RouletteRoom:
    players: list[str] = field(default_factory=list)
    names: dict[str, str] = field(default_factory=dict)
    chamber: int = 0
    turn: int = 0
    shots: int = 0
    active: bool = False

    def join(self, user_id: str, nickname: str) -> str:
        if self.active:
            return "本局已经开始，不能中途加入。"
        if user_id in self.players:
            return f"{nickname} 已经在房间里了。"
        if len(self.players) >= 8:
            return "轮盘赌房间最多容纳 8 人。"
        self.players.append(user_id)
        self.names[user_id] = nickname
        return f"{nickname} 加入成功，当前玩家：{self.player_list()}"

    def player_list(self) -> str:
        return "、".join(self.names[user_id] for user_id in self.players)

    def start(self) -> str:
        if self.active:
            return "本局已经开始，请等待当前玩家行动。"
        if len(self.players) < 2:
            return "多人轮盘赌至少需要 2 名玩家，请先使用 /轮盘赌 加入。"
        self.chamber = random.randint(1, 6)
        self.turn = 0
        self.shots = 0
        self.active = True
        return f"多人轮盘赌开始！玩家：{self.player_list()}\n请 {self.names[self.players[0]]} 使用 /轮盘赌 开枪。"

    def shoot(self, user_id: str) -> str:
        if not self.active:
            return "当前没有进行中的多人轮盘赌。使用 /轮盘赌 多人 创建房间。"
        current_user = self.players[self.turn]
        if user_id != current_user:
            return f"还没轮到你，请等待 {self.names[current_user]}。"

        self.shots += 1
        player_name = self.names[current_user]
        if self.shots == self.chamber:
            self.active = False
            return f"{player_name} 扣动扳机……砰！本轮结束。\n使用 /轮盘赌 多人 重新开局。"

        self.turn = (self.turn + 1) % len(self.players)
        next_name = self.names[self.players[self.turn]]
        return f"{player_name} 扣动扳机……咔哒，安全！\n轮到 {next_name}，请使用 /轮盘赌 开枪。"

    def status(self) -> str:
        if not self.players:
            return "当前没有轮盘赌房间。"
        state = "进行中" if self.active else "等待开始"
        result = f"轮到：{self.names[self.players[self.turn]]}" if self.active else ""
        return f"轮盘赌房间（{state}）\n玩家：{self.player_list()}\n{result}".strip()


ROULETTE_ROOMS: dict[str, RouletteRoom] = {}


def roulette_command(room_id: str, user_id: str, nickname: str, action: str) -> str:
    """处理轮盘赌命令。"""
    action = action.strip().lower()
    if action in {"", "单人", "solo"}:
        return solo_roulette()
    if action in {"多人", "创建", "新建", "multi"}:
        ROULETTE_ROOMS[room_id] = RouletteRoom()
        return "已创建多人轮盘赌房间。其他玩家请使用 /轮盘赌 加入，人数足够后由任意玩家使用 /轮盘赌 开始。"

    room = ROULETTE_ROOMS.get(room_id)
    if action in {"加入", "join"}:
        if room is None:
            return "还没有房间，请先使用 /轮盘赌 多人。"
        return room.join(user_id, nickname)
    if action in {"开始", "start"}:
        if room is None:
            return "还没有房间，请先使用 /轮盘赌 多人。"
        return room.start()
    if action in {"开枪", "射击", "shoot"}:
        if room is None:
            return "还没有进行中的房间，请先使用 /轮盘赌 多人。"
        return room.shoot(user_id)
    if action in {"状态", "status"}:
        return room.status() if room else "当前没有轮盘赌房间。"
    if action in {"退出", "结束", "reset"}:
        ROULETTE_ROOMS.pop(room_id, None)
        return "轮盘赌房间已结束。"
    return "用法：/轮盘赌（单人）或 /轮盘赌 多人、加入、开始、开枪、状态、退出。"


SUITS = ("♠", "♥", "♦", "♣")
RANKS = ("A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K")
CARD_VALUES = {"A": 11, "J": 10, "Q": 10, "K": 10, **{str(i): i for i in range(2, 11)}}


def _new_deck() -> list[str]:
    deck = [f"{suit}{rank}" for suit in SUITS for rank in RANKS]
    random.shuffle(deck)
    return deck


def _rank(card: str) -> str:
    return card[1:]


def hand_score(hand: list[str]) -> int:
    score = sum(CARD_VALUES[_rank(card)] for card in hand)
    aces = sum(_rank(card) == "A" for card in hand)
    while score > 21 and aces:
        score -= 10
        aces -= 1
    return score


def _hand_text(hand: list[str]) -> str:
    return " ".join(hand) if hand else "无"


@dataclass
class BlackjackRoom:
    players: list[str] = field(default_factory=list)
    names: dict[str, str] = field(default_factory=dict)
    hands: dict[str, list[str]] = field(default_factory=dict)
    deck: list[str] = field(default_factory=list)
    dealer: list[str] = field(default_factory=list)
    turn: int = 0
    stood: set[str] = field(default_factory=set)
    active: bool = False
    finished: bool = False

    def join(self, user_id: str, nickname: str) -> str:
        if self.active:
            return "21 点已经开始，不能中途加入。"
        if user_id in self.players:
            return f"{nickname} 已经加入了。"
        if len(self.players) >= 6:
            return "多人 21 点最多 6 名玩家。"
        self.players.append(user_id)
        self.names[user_id] = nickname
        return f"{nickname} 加入成功，当前玩家：{self.player_list()}"

    def player_list(self) -> str:
        return "、".join(self.names[user_id] for user_id in self.players)

    def start(self) -> str:
        if self.active:
            return "21 点已经开始。"
        if len(self.players) < 2:
            return "多人 21 点至少需要 2 名玩家。"
        self.deck = _new_deck()
        self.hands = {user_id: [self.deck.pop(), self.deck.pop()] for user_id in self.players}
        self.dealer = [self.deck.pop(), self.deck.pop()]
        self.turn = 0
        self.stood = set()
        self.active = True
        self.finished = False
        first = self.players[0]
        return f"21 点开始！玩家：{self.player_list()}\n庄家明牌：{self.dealer[0]}，当前轮到 {self.names[first]}。\n请使用 /21点 要牌 或 /21点 停牌。"

    def _advance(self) -> str:
        while self.turn < len(self.players) and (self.players[self.turn] in self.stood or hand_score(self.hands[self.players[self.turn]]) > 21):
            self.turn += 1
        if self.turn < len(self.players):
            return f"轮到 {self.names[self.players[self.turn]]}，请使用 /21点 要牌 或 /21点 停牌。"
        return self._finish()

    def hit(self, user_id: str) -> str:
        if not self.active:
            return "当前没有进行中的 21 点。"
        current = self.players[self.turn] if self.turn < len(self.players) else None
        if user_id != current:
            return f"还没轮到你，请等待 {self.names[current]}。" if current else "本局即将结算。"
        card = self.deck.pop()
        hand = self.hands[user_id]
        hand.append(card)
        score = hand_score(hand)
        message = f"{self.names[user_id]} 要牌：{card}，当前点数 {score}。"
        if score > 21:
            self.stood.add(user_id)
            message += " 爆牌，自动停牌。"
        elif score == 21:
            self.stood.add(user_id)
            message += " 21 点，自动停牌。"
        else:
            return message + "\n" + self._advance()
        return message + "\n" + self._advance()

    def stand(self, user_id: str) -> str:
        if not self.active:
            return "当前没有进行中的 21 点。"
        current = self.players[self.turn] if self.turn < len(self.players) else None
        if user_id != current:
            return f"还没轮到你，请等待 {self.names[current]}。" if current else "本局即将结算。"
        self.stood.add(user_id)
        return f"{self.names[user_id]} 选择停牌。\n" + self._advance()

    def _finish(self) -> str:
        while hand_score(self.dealer) < 17:
            self.dealer.append(self.deck.pop())
        dealer_score = hand_score(self.dealer)
        lines = [f"庄家手牌：{_hand_text(self.dealer)}，点数：{dealer_score}", "本局结算："]
        for user_id in self.players:
            score = hand_score(self.hands[user_id])
            if score > 21:
                result = "爆牌，输"
            elif dealer_score > 21 or score > dealer_score:
                result = "胜利"
            elif score == dealer_score:
                result = "平局"
            else:
                result = "失败"
            lines.append(f"{self.names[user_id]}：{_hand_text(self.hands[user_id])}（{score} 点，{result}）")
        self.active = False
        self.finished = True
        return "\n".join(lines) + "\n使用 /21点 创建 开始新一局。"

    def status(self) -> str:
        if not self.players:
            return "当前没有 21 点房间。"
        lines = [f"21 点房间（{'进行中' if self.active else '等待开始'}）", f"玩家：{self.player_list()}"]
        if self.active:
            lines.append(f"庄家明牌：{self.dealer[0]}")
            for user_id in self.players:
                lines.append(f"{self.names[user_id]}：{_hand_text(self.hands[user_id])}（{hand_score(self.hands[user_id])} 点）")
            if self.turn < len(self.players):
                lines.append(f"当前轮次：{self.names[self.players[self.turn]]}")
        return "\n".join(lines)


BLACKJACK_ROOMS: dict[str, BlackjackRoom] = {}


def blackjack_command(room_id: str, user_id: str, nickname: str, action: str) -> str:
    """处理多人 21 点命令。"""
    action = action.strip().lower()
    if action in {"创建", "多人", "新建", "create"}:
        BLACKJACK_ROOMS[room_id] = BlackjackRoom()
        return "已创建多人 21 点房间。其他玩家使用 /21点 加入，人数足够后使用 /21点 开始。"
    room = BLACKJACK_ROOMS.get(room_id)
    if action in {"加入", "join"}:
        return room.join(user_id, nickname) if room else "还没有房间，请先使用 /21点 创建。"
    if action in {"开始", "start"}:
        return room.start() if room else "还没有房间，请先使用 /21点 创建。"
    if action in {"要牌", "要", "hit"}:
        return room.hit(user_id) if room else "还没有进行中的 21 点。"
    if action in {"停牌", "停", "stand"}:
        return room.stand(user_id) if room else "还没有进行中的 21 点。"
    if action in {"状态", "查看", "status"}:
        return room.status() if room else "当前没有 21 点房间。"
    if action in {"退出", "结束", "reset"}:
        BLACKJACK_ROOMS.pop(room_id, None)
        return "21 点房间已结束。"
    return "用法：/21点 创建、加入、开始、要牌、停牌、状态、退出。"
