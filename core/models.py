import json
from dataclasses import dataclass, asdict
from typing import Optional

@dataclass
class Episode:
    program_name: str
    channel: str
    title: str
    url: str
    broadcast_time: str = ""

    def format_output(self) -> str:
        """指定の出力フォーマットに変換する"""
        time_str = f" {self.broadcast_time}" if self.broadcast_time else ""
        return f"●{self.program_name}({self.channel}{time_str})\n・{self.title}\n{self.url}"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Episode":
        return cls(**data)
