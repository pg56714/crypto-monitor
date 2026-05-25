"""Entry engine tests."""

import unittest

from src.scoring.entry_engine import build_entry_plan


class EntryPlanTests(unittest.TestCase):
    """Tests for accumulation entry-plan price handling."""

    def test_uses_current_price_as_entry_price(self) -> None:
        """Use current price as the entry price when it is inside the entry zone."""
        plan = build_entry_plan(
            avg_whale_price=(0.0944 + 0.1623) / 2,
            support=0.0944,
            resistance=0.1623,
            volume_spike=True,
            whale_inflow=True,
            current_price=0.1026,
        )

        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertTrue(plan.is_valid)
        self.assertEqual(plan.entry_price, 0.1026)
        self.assertGreaterEqual(plan.risk_reward, 2.0)

    def test_rejects_entry_when_current_price_is_above_entry_zone(self) -> None:
        """Reject the plan when current price is above the risk-reward entry zone."""
        plan = build_entry_plan(
            avg_whale_price=(0.0944 + 0.1623) / 2,
            support=0.0944,
            resistance=0.1623,
            volume_spike=True,
            whale_inflow=True,
            current_price=0.13,
        )

        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertFalse(plan.is_valid)

    def test_rejects_entry_when_current_price_is_below_support(self) -> None:
        """Reject the plan when price has already fallen below the support entry zone."""
        plan = build_entry_plan(
            avg_whale_price=(0.0944 + 0.1623) / 2,
            support=0.0944,
            resistance=0.1623,
            volume_spike=True,
            whale_inflow=True,
            current_price=0.09,
        )

        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertFalse(plan.is_valid)


if __name__ == "__main__":
    unittest.main()
