import unittest
from factory.taskgraph import TaskGraph, TaskGraphError


class TaskGraphTests(unittest.TestCase):
    def valid(self):
        return {"tasks": [
            {"id": "T1", "profile": "lite", "depends_on": [], "acceptance": ["one passes"], "scope": []},
            {"id": "T2", "profile": "pro", "depends_on": ["T1"], "acceptance": ["two passes"], "scope": ["src/**"]},
        ]}

    def test_valid_graph_orders_dependencies(self):
        graph = TaskGraph(self.valid())
        self.assertEqual([task["id"] for task in graph.order()], ["T1", "T2"])

    def test_empty_graph_is_rejected(self):
        with self.assertRaises(TaskGraphError):
            TaskGraph({"tasks": []})

    def test_missing_acceptance_is_rejected(self):
        data = self.valid(); data["tasks"][0]["acceptance"] = []
        with self.assertRaises(TaskGraphError):
            TaskGraph(data)

    def test_unsafe_task_id_is_rejected(self):
        data = self.valid(); data["tasks"][0]["id"] = "../escape"
        with self.assertRaises(TaskGraphError):
            TaskGraph(data)

    def test_unknown_dependency_is_rejected(self):
        data = self.valid(); data["tasks"][1]["depends_on"] = ["missing"]
        with self.assertRaises(TaskGraphError):
            TaskGraph(data)

    def test_cycle_is_rejected(self):
        data = self.valid(); data["tasks"][0]["depends_on"] = ["T2"]
        with self.assertRaises(TaskGraphError):
            TaskGraph(data)

    def test_profile_must_be_lite_or_pro(self):
        data = self.valid(); data["tasks"][0]["profile"] = "factory"
        with self.assertRaises(TaskGraphError):
            TaskGraph(data)


if __name__ == "__main__":
    unittest.main()
