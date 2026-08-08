import unittest
from factory.taskgraph import TaskGraph, TaskGraphError


class TaskGraphTests(unittest.TestCase):
    def test_valid_graph_orders_dependencies(self):
        graph=TaskGraph({"tasks":[
            {"id":"A","profile":"lite","depends_on":[],"acceptance":["A passes"]},
            {"id":"B","profile":"pro","depends_on":["A"],"acceptance":["B passes"]},
        ]})
        self.assertEqual([x["id"] for x in graph.order()],["A","B"])

    def test_empty_missing_id_and_missing_acceptance_fail_closed(self):
        for payload in [
            {"tasks":[]},
            {"tasks":[{"profile":"lite","depends_on":[],"acceptance":["x"]}]},
            {"tasks":[{"id":"A","profile":"lite","depends_on":[]}]},
        ]:
            with self.subTest(payload=payload), self.assertRaises(TaskGraphError):
                TaskGraph(payload)

    def test_duplicate_unknown_dependency_invalid_profile_and_cycle_fail(self):
        cases=[
            {"tasks":[
                {"id":"A","profile":"lite","depends_on":[],"acceptance":["x"]},
                {"id":"A","profile":"lite","depends_on":[],"acceptance":["y"]},
            ]},
            {"tasks":[{"id":"A","profile":"lite","depends_on":["X"],"acceptance":["x"]}]},
            {"tasks":[{"id":"A","profile":"factory","depends_on":[],"acceptance":["x"]}]},
            {"tasks":[
                {"id":"A","profile":"lite","depends_on":["B"],"acceptance":["x"]},
                {"id":"B","profile":"lite","depends_on":["A"],"acceptance":["y"]},
            ]},
        ]
        for payload in cases:
            with self.subTest(payload=payload), self.assertRaises(TaskGraphError):
                TaskGraph(payload)


if __name__=="__main__":
    unittest.main()
