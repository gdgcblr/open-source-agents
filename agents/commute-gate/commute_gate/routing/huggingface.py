from __future__ import annotations

from commute_gate.models import CommuteSlots, RoutePlan


class HuggingFaceRouteProvider:
    """Optional adapter. No Bengaluru transit GTFS exists on Hugging Face as of 2026-10."""

    name = "huggingface"

    def __init__(self, dataset_name: str) -> None:
        self.dataset_name = dataset_name

    def get_routes(self, slots: CommuteSlots) -> RoutePlan:
        if not self.dataset_name:
            raise ValueError(
                "No Hugging Face Bengaluru transit dataset is configured. "
                "HF_DATASET is empty. Use ROUTE_PROVIDER=bengaluru (BMTC GTFS + Namma Metro) "
                "or set HF_DATASET to a public dataset that contains origin/destination routes."
            )
        try:
            from datasets import load_dataset  # type: ignore
        except ImportError as exc:
            raise ValueError(
                "Install optional extra `datasets` to use Hugging Face: pip install datasets"
            ) from exc

        table = load_dataset(self.dataset_name, split="train")
        origin = (slots.origin or "").lower()
        dest = (slots.destination or "").lower()
        for row in table:
            row_origin = str(row.get("origin") or row.get("from") or "").lower()
            row_dest = str(row.get("destination") or row.get("to") or "").lower()
            if origin in row_origin and dest in row_dest:
                from commute_gate.models import RouteLeg

                duration = int(row.get("duration_min") or row.get("duration") or 0)
                departure = str(row.get("departure") or slots.leave_by or "08:00")
                arrival = str(row.get("arrival") or "")
                return RoutePlan(
                    origin=slots.origin or "",
                    destination=slots.destination or "",
                    legs=[
                        RouteLeg(
                            mode=str(row.get("mode") or "bus"),
                            line=str(row.get("line") or row.get("route") or "HF"),
                            duration_min=duration,
                            departure=departure,
                        )
                    ],
                    total_duration_min=duration,
                    arrival=arrival,
                    raw={"provider": self.name, "dataset": self.dataset_name, "row": dict(row)},
                )
        raise ValueError(f"No Hugging Face row matched {slots.origin} → {slots.destination}.")
