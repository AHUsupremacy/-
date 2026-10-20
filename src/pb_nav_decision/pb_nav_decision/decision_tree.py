"""A binary decision tree with a condition node and two goal leaves."""

from dataclasses import dataclass
from typing import Callable, Union


@dataclass(frozen=True)
class RobotHealth:
    remain_hp: int
    max_hp: int

    @property
    def valid(self) -> bool:
        return self.max_hp > 0 and 0 <= self.remain_hp <= self.max_hp


@dataclass(frozen=True)
class GoalLeaf:
    name: str

    def evaluate(self, health: RobotHealth) -> str:
        return self.name


@dataclass(frozen=True)
class ConditionNode:
    condition: Callable[[RobotHealth], bool]
    when_true: Union['ConditionNode', GoalLeaf]
    when_false: Union['ConditionNode', GoalLeaf]

    def evaluate(self, health: RobotHealth) -> str:
        child = self.when_true if self.condition(health) else self.when_false
        return child.evaluate(health)


class HealthDecisionTree:
    def __init__(self, threshold: int):
        if threshold < 0:
            raise ValueError('hp_threshold must be nonnegative')
        self.root = ConditionNode(
            lambda health: health.remain_hp > threshold,
            GoalLeaf('target_one'),
            GoalLeaf('target_two'),
        )

    def evaluate(self, health: RobotHealth) -> str:
        if not health.valid:
            raise ValueError('Require max_hp > 0 and 0 <= remain_hp <= max_hp')
        return self.root.evaluate(health)
