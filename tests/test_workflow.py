import importlib.util
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


SCRIPT_DIR = Path(__file__).parents[1] / "scripts"
SCRIPT_PATH = SCRIPT_DIR / "workflow.py"


def load_workflow():
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    spec = importlib.util.spec_from_file_location("workflow_under_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class WorkflowTests(unittest.TestCase):
    def test_resume_enables_visual_review_gate_for_formal_production(self):
        workflow = load_workflow()
        with TemporaryDirectory() as temp:
            project = Path(temp)
            book_dir = project / "books" / "b01" / "v1"
            queue_path = book_dir / "review" / "production-queue.json"
            state = {
                "book_dir": str(book_dir),
                "page_count": 1,
                "max_in_flight": 1,
                "requires_user_authorization": True,
                "jobs": [{"page": 1, "status": "pending"}],
            }
            with patch.object(workflow, "_book_and_queue", return_value=(book_dir, queue_path)), patch.object(
                workflow, "init_queue", return_value=state
            ) as init_queue:
                result = workflow.resume(project, "b01", version="v1")

            self.assertEqual(result["status"], "authorization_required")
            self.assertTrue(init_queue.call_args.kwargs["require_visual_review"])

    def test_resume_reports_pending_unknown_before_generic_failed_page(self):
        workflow = load_workflow()
        with TemporaryDirectory() as temp:
            project = Path(temp)
            book_dir = project / "books" / "b03" / "v1"
            queue_path = book_dir / "review" / "production-queue.json"
            state = {
                "book_dir": str(book_dir),
                "page_count": 3,
                "max_in_flight": 1,
                "requires_user_authorization": True,
                "jobs": [
                    {"page": 1, "status": "cached"},
                    {"page": 2, "status": "cached"},
                    {"page": 3, "status": "failed", "current_request_id": "request-3"},
                ],
                "request_lifecycle": [
                    {"request_id": "request-3", "page": 3, "terminal_state": "pending_unknown"}
                ],
            }
            with patch.object(workflow, "_book_and_queue", return_value=(book_dir, queue_path)), patch.object(
                workflow, "init_queue", return_value=state
            ):
                result = workflow.resume(project, "b03", version="v1")

            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["reason"], "manual_intervention_required")
            self.assertEqual(result["blocked_pages"], [3])
            self.assertIn("claim-recovery", result["next_action"])


if __name__ == "__main__":
    unittest.main()
