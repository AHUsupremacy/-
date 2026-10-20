import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pb_nav_decision.decision_tree import HealthDecisionTree, RobotHealth
from pb_nav_decision.goal_store import (
    StoredGoal,
    append_latest,
    load_goal_history,
    load_goals,
    save_goals,
)


class DecisionTreeTests(unittest.TestCase):
    def temporary_directory(self):
        workspace = Path(__file__).resolve().parents[3]
        temp_root = workspace / 'runtime' / 'tmp'
        temp_root.mkdir(parents=True, exist_ok=True)
        return TemporaryDirectory(dir=temp_root)

    def test_high_selects_one(self):
        self.assertEqual(HealthDecisionTree(250).evaluate(RobotHealth(500, 500)), 'target_one')

    def test_low_selects_two(self):
        self.assertEqual(HealthDecisionTree(250).evaluate(RobotHealth(100, 500)), 'target_two')

    def test_threshold_equality_selects_two(self):
        tree = HealthDecisionTree(250)
        self.assertEqual(tree.evaluate(RobotHealth(251, 500)), 'target_one')
        self.assertEqual(tree.evaluate(RobotHealth(250, 500)), 'target_two')
        self.assertEqual(tree.evaluate(RobotHealth(249, 500)), 'target_two')

    def test_zero_hp_is_a_valid_low_value(self):
        self.assertEqual(HealthDecisionTree(250).evaluate(RobotHealth(0, 500)), 'target_two')

    def test_invalid_status_cannot_select_a_goal(self):
        for health in (RobotHealth(-1, 500), RobotHealth(501, 500), RobotHealth(0, 0)):
            with self.subTest(health=health), self.assertRaises(ValueError):
                HealthDecisionTree(250).evaluate(health)

    def test_threshold_is_configurable(self):
        self.assertEqual(HealthDecisionTree(50).evaluate(RobotHealth(100, 500)), 'target_one')

    def test_negative_threshold_is_invalid(self):
        with self.assertRaises(ValueError):
            HealthDecisionTree(-1)

    def test_goal_store_keeps_two_slots_and_loads_them(self):
        with self.temporary_directory() as directory:
            path = str(Path(directory) / 'goals.json')
            first = StoredGoal(1.0, 2.0, 0.1)
            second = StoredGoal(3.0, 4.0, 0.2)
            save_goals(path, [first, second])
            self.assertEqual(load_goals(path), (first, second))

    def test_goal_store_requires_both_points_for_decision(self):
        with self.temporary_directory() as directory:
            path = str(Path(directory) / 'goals.json')
            save_goals(path, [StoredGoal(1.0, 2.0, 0.1), None])
            self.assertEqual(load_goal_history(path), (StoredGoal(1.0, 2.0, 0.1), None))
            with self.assertRaises(ValueError):
                load_goals(path)

    def test_goal_history_retains_latest_two_in_order(self):
        first = StoredGoal(1.0, 0.0, 0.0)
        second = StoredGoal(2.0, 0.0, 0.0)
        third = StoredGoal(3.0, 0.0, 0.0)
        history, slot = append_latest([None, None], first)
        self.assertEqual((history, slot), ([first, None], 'point_one'))
        history, slot = append_latest(history, second)
        self.assertEqual((history, slot), ([first, second], 'point_two'))
        history, slot = append_latest(history, third)
        self.assertEqual((history, slot), ([second, third], 'point_two (oldest point moved to point_one)'))
