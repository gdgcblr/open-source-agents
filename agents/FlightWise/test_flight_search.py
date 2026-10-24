import unittest

from FlightWise.flight_search import search_flights


class SearchFlightsTests(unittest.TestCase):
    def test_returns_five_ranked_mock_results_for_round_trip(self):
        response = search_flights(
            "BLR",
            "DEL",
            "2026-12-01",
            return_date="2026-12-08",
            passengers=2,
            budget=30000,
            checked_bags=1,
            carry_on_required=True,
        )

        self.assertEqual(response["status"], "success")
        self.assertEqual(response["source"], "synthetic_mock")
        self.assertEqual(response["query"]["trip_type"], "round_trip")
        self.assertEqual(len(response["results"]), 5)
        self.assertEqual([flight["rank"] for flight in response["results"]], [1, 2, 3, 4, 5])
        self.assertTrue(all(flight["return_date"] == "2026-12-08" for flight in response["results"]))
        self.assertTrue(all(flight["currency"] == "INR" for flight in response["results"]))
        self.assertTrue(all(flight["source"] == "synthetic_mock" for flight in response["results"]))
        self.assertTrue(all(0 <= flight["score"] <= 100 for flight in response["results"]))

    def test_one_way_price_is_total_for_all_passengers(self):
        response = search_flights(
            "BLR",
            "DEL",
            "2026-12-01",
            passengers=2,
        )

        self.assertEqual(response["query"]["trip_type"], "one_way")
        self.assertIsNone(response["results"][0]["return_date"])
        self.assertEqual(
            response["results"][0]["total_price"],
            response["results"][0]["price_per_passenger"] * 2,
        )

    def test_prioritizes_within_budget_results(self):
        response = search_flights(
            "BLR",
            "DEL",
            "2026-12-01",
            budget=5000,
            priority="cheapest",
        )
        results = response["results"]

        self.assertEqual(results[0]["budget_status"], "within_budget")
        self.assertTrue(all(flight["budget_status"] == "over_budget" for flight in results[1:]))

    def test_rejects_invalid_date_and_unsupported_currency(self):
        invalid_date = search_flights("BLR", "DEL", "tomorrow")
        unsupported_currency = search_flights(
            "BLR", "DEL", "2026-12-01", currency="USD"
        )

        self.assertEqual(invalid_date["status"], "error")
        self.assertIn("YYYY-MM-DD", invalid_date["message"])
        self.assertEqual(unsupported_currency["status"], "error")
        self.assertIn("INR only", unsupported_currency["message"])


if __name__ == "__main__":
    unittest.main()
