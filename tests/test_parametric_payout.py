"""
Local tests for parametric_payout.py. Run from the project root:

    python3 -m unittest discover -s tests -v
"""
import importlib.util
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import genlayer_stub as stub  # noqa: E402

gl = stub.install()

spec = importlib.util.spec_from_file_location(
    "parametric_payout", os.path.join(HERE, "..", "parametric_payout.py")
)
pp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pp)


def llm(found=True, value=0, reason="ok"):
    return json.dumps({"found": found, "value": value, "reason": reason})


class Base(unittest.TestCase):
    def setUp(self):
        stub.reset()
        self.c = pp.ParametricPayout()
        self.c.__init__()

    def make(self, pid="p1", comparator="GTE", threshold=30, tolerance=5,
             amount=100, max_checks=3):
        return self.c.create_policy(
            pid, "https://example.com/flight", "Delay in minutes of flight AB123",
            comparator, threshold, tolerance, amount, max_checks,
        )

    def policy(self, pid="p1"):
        return json.loads(self.c.get_policy(pid))

    def run_check(self, leader_llm, validator_llm=None, pid="p1"):
        stub._Nondet.llm_queue = [leader_llm, validator_llm if validator_llm is not None else leader_llm]
        return self.c.check_policy(pid)


class TestCreatePolicy(Base):
    def test_creates_active_policy(self):
        self.make()
        p = self.policy()
        self.assertEqual(p["status"], "ACTIVE")
        self.assertEqual(p["holder"], "0xHOLDER")
        self.assertEqual(p["checks_used"], 0)
        self.assertEqual(json.loads(self.c.get_policy_ids()), ["p1"])
        self.assertEqual(json.loads(self.c.get_check_log("p1")), [])

    def test_rejects_bad_inputs(self):
        bad = [
            dict(pid=""), dict(comparator="EQ"), dict(tolerance=-1),
            dict(amount=0), dict(max_checks=0), dict(max_checks=6),
        ]
        for kwargs in bad:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(Exception):
                    self.make(**kwargs)

    def test_rejects_bad_url_and_short_prompt(self):
        with self.assertRaises(Exception):
            self.c.create_policy("x", "ftp://bad", "metric text", "GTE", 1, 0, 1, 1)
        with self.assertRaises(Exception):
            self.c.create_policy("x", "https://ok.com", "abc", "GTE", 1, 0, 1, 1)

    def test_rejects_duplicate_id(self):
        self.make()
        with self.assertRaises(Exception):
            self.make()


class TestOutcomes(Base):
    def test_triggered_pays_and_locks(self):
        self.make()
        self.assertEqual(self.run_check(llm(value=45)), "TRIGGERED")
        p = self.policy()
        self.assertEqual(p["status"], "PAID")
        self.assertEqual(p["last_value"], 45)
        self.assertEqual(self.c.get_total_paid(), 100)

    def test_double_claim_is_blocked(self):
        self.make()
        self.run_check(llm(value=45))
        with self.assertRaises(Exception):
            self.run_check(llm(value=45))
        self.assertEqual(self.c.get_total_paid(), 100)  # paid exactly once

    def test_not_triggered_stays_active(self):
        self.make()
        self.assertEqual(self.run_check(llm(value=10)), "NOT_TRIGGERED")
        p = self.policy()
        self.assertEqual(p["status"], "ACTIVE")
        self.assertEqual(p["checks_used"], 1)
        self.assertEqual(self.c.get_total_paid(), 0)

    def test_expires_after_max_checks(self):
        self.make(max_checks=2)
        self.run_check(llm(value=10))
        self.run_check(llm(value=12))
        self.assertEqual(self.policy()["status"], "EXPIRED")
        with self.assertRaises(Exception):
            self.run_check(llm(value=99))
        self.assertEqual(self.c.get_total_paid(), 0)

    def test_metric_missing_is_unresolved(self):
        self.make()
        self.assertEqual(self.run_check(llm(found=False, reason="not on page")), "UNRESOLVED")
        p = self.policy()
        self.assertEqual(p["status"], "ACTIVE")
