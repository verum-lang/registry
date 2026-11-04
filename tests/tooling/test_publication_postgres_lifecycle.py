"""Ownership and timeout controls for the isolated PostgreSQL test runner."""

from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))
import test_publication_postgres as runner


class OwnedContainerTests(unittest.TestCase):
    def test_only_exact_owned_name_is_removed(self):
        responses = [subprocess.CompletedProcess([], 0, "owner-token\n", ""),
                     subprocess.CompletedProcess([], 0, "", "")]
        with patch.object(runner.subprocess, "run", side_effect=responses) as command:
            runner.remove_owned_container("my-exact-container", "owner-token", 7)
        self.assertEqual(command.call_args_list[1].args[0],
                         ["docker", "rm", "-fv", "my-exact-container"])
        self.assertTrue(all(call.kwargs["timeout"] == 7 for call in command.call_args_list))

    def test_foreign_label_never_authorizes_removal(self):
        response = subprocess.CompletedProcess([], 0, "another-owner\n", "")
        with patch.object(runner.subprocess, "run", return_value=response) as command:
            with self.assertRaisesRegex(RuntimeError, "another owner"):
                runner.remove_owned_container("my-exact-container", "owner-token", 7)
        self.assertEqual(command.call_count, 1)

    def test_unavailable_daemon_never_means_absent_container(self):
        response = subprocess.CompletedProcess([], 1, "", "Cannot connect to Docker daemon")
        with patch.object(runner.subprocess, "run", return_value=response) as command:
            with self.assertRaisesRegex(RuntimeError, "could not confirm cleanup ownership"):
                runner.remove_owned_container("my-exact-container", "owner-token", 7)
        self.assertEqual(command.call_count, 1)

    def test_cleanup_timeout_is_a_failure(self):
        responses = [subprocess.CompletedProcess([], 0, "owner-token\n", ""),
                     subprocess.TimeoutExpired(["docker", "rm"], 7)]
        with patch.object(runner.subprocess, "run", side_effect=responses):
            with self.assertRaises(subprocess.TimeoutExpired):
                runner.remove_owned_container("my-exact-container", "owner-token", 7)

    def test_launcher_timeout_retains_name_for_cleanup_and_never_runs_sql(self):
        responses = [subprocess.TimeoutExpired(["docker", "run"], 7),
                     subprocess.CompletedProcess([], 1, "", "Error: No such object: missing")]
        with patch.object(runner.subprocess, "run", side_effect=responses) as command, \
                patch.object(runner.socket, "socket") as socket, \
                patch.object(sys, "argv", ["test_publication_postgres.py", sys.executable,
                                          "--component", "projection-sql", "--docker-timeout", "7"]):
            socket.return_value.__enter__.return_value.getsockname.return_value = ("127.0.0.1", 43210)
            with self.assertRaises(subprocess.TimeoutExpired):
                runner.main()
        self.assertEqual(command.call_count, 2)
        launch = command.call_args_list[0]
        name = launch.args[0][launch.args[0].index("--name") + 1]
        self.assertEqual(launch.kwargs["timeout"], 7)
        self.assertEqual(command.call_args_list[1].args[0][-1], name)
        self.assertEqual(command.call_args_list[1].kwargs["timeout"], 7)


if __name__ == "__main__":
    unittest.main()
