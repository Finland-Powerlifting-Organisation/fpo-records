#!/usr/bin/env python3

import argparse
import csv
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


FILE_PATTERN = re.compile(r"^(\d{4})(?:-(\d{2})-(\d{2}))?\.csv$")


@dataclass
class ParsedRow:
	key: str
	weight: float
	name: str
	location: str


@dataclass
class IncreaseEvent:
	name: str
	key: str
	location: str
	previous: float
	new: float
	delta: float
	source_file: str


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(
		description="Generate a Spotify Wrapped style records report for a year."
	)
	parser.add_argument(
		"year",
		type=int,
		help="Year to report on (e.g. 2024)",
	)
	parser.add_argument(
		"--root",
		type=Path,
		default=Path("."),
		help="Directory containing the CSV event files (defaults to cwd).",
	)
	return parser.parse_args()


def parse_filename(path: Path) -> Optional[Tuple[int, int, int]]:
	match = FILE_PATTERN.match(path.name)
	if not match:
		return None
	year = int(match.group(1))
	month = int(match.group(2) or 0)
	day = int(match.group(3) or 0)
	return year, month, day


def sorted_event_files(root: Path) -> List[Tuple[Tuple[int, int, int], Path]]:
	files: List[Tuple[Tuple[int, int, int], Path]] = []
	for path in root.iterdir():
		if not path.is_file():
			continue
		parsed = parse_filename(path)
		if parsed is None:
			continue
		files.append((parsed, path))
	files.sort(key=lambda item: (item[0][0], item[0][1], item[0][2], item[1].name))
	return files


def read_rows(path: Path) -> Iterable[ParsedRow]:
	with path.open(newline="", encoding="utf-8") as handle:
		reader = csv.reader(handle)
		for row in reader:
			if not row or len(row) < 3:
				continue
			key = row[0].strip()
			try:
				weight = float(row[1])
			except ValueError:
				continue
			name = row[2].strip()
			location = row[4].strip() if len(row) > 4 else ""
			yield ParsedRow(key=key, weight=weight, name=name, location=location)


def is_tested(key: str) -> bool:
	parts = key.split("|")
	if len(parts) < 2:
		return False
	return parts[1].endswith("-D")


def build_report(target_year: int, root: Path) -> Dict[str, object]:
	records: Dict[str, float] = {}
	total_broken = 0
	new_records = 0
	location_counts: Counter[str] = Counter()
	name_counts: Counter[str] = Counter()
	name_counts_untested: Counter[str] = Counter()
	increase_events: List[IncreaseEvent] = []
	total_increase = 0.0
	files = sorted_event_files(root)

	for (year, _month, _day), path in files:
		for row in read_rows(path):
			prev_weight = records.get(row.key)
			is_new_best = prev_weight is None or row.weight > prev_weight
			if is_new_best and year == target_year:
				total_broken += 1
				location_counts[row.location] += 1
				name_counts[row.name] += 1
				if not is_tested(row.key):
					name_counts_untested[row.name] += 1
				if prev_weight is None:
					new_records += 1
				else:
					delta = row.weight - prev_weight
					total_increase += delta
					increase_events.append(
						IncreaseEvent(
							name=row.name,
							key=row.key,
							location=row.location,
							previous=prev_weight,
							new=row.weight,
							delta=delta,
							source_file=path.name,
						)
					)
			if is_new_best:
				records[row.key] = row.weight

	return {
		"total_broken": total_broken,
		"new_records": new_records,
		"location_counts": location_counts,
		"name_counts": name_counts,
		"name_counts_untested": name_counts_untested,
		"increase_events": increase_events,
		"total_increase": total_increase,
	}


def format_counter(counter: Counter[str], title: str, limit: int = 10) -> str:
	lines = [title]
	for idx, (name, count) in enumerate(counter.most_common(limit), start=1):
		lines.append(f"{idx:2d}. {name} — {count}")
	if len(lines) == 1:
		lines.append("   (no data)")
	return "\n".join(lines)


def format_increases(events: List[IncreaseEvent], limit: int = 10) -> str:
	if not events:
		return "Biggest glow-ups (no qualifying improvements)"
	sorted_events = sorted(
		events,
		key=lambda item: (item.delta, item.new, item.name),
		reverse=True,
	)
	lines = ["Biggest glow-ups (excluding brand new records)"]
	for idx, event in enumerate(sorted_events[:limit], start=1):
		lines.append(
			f"{idx:2d}. {event.name} ({event.key}) +{event.delta:.1f} "
			f"→ {event.new:.1f} at {event.location} [{event.source_file}]"
		)
	return "\n".join(lines)


def suggest_extra_stats(report: Dict[str, object]) -> List[str]:
	total_broken = report["total_broken"]
	new_records = report["new_records"]
	total_increase = report["total_increase"]
	unique_people = len(report["name_counts"])
	extra = [
		f"Total kg added to existing records: {total_increase:.1f}",
		f"Fresh records set from scratch: {new_records}",
		f"Distinct lifters hitting the board: {unique_people}",
	]
	return extra


def print_report(year: int, report: Dict[str, object]) -> None:
	print(f"FPO Records Wrapped {year}")
	print("=" * 40)
	print(f"Records broken (all divisions): {report['total_broken']}")
	print()
	print(format_counter(report["location_counts"], "Where the magic happened (top 10)"))
	print()
	print(format_counter(report["name_counts"], "All-time hitters (tested + untested, top 10)"))
	print()
	print(format_counter(report["name_counts_untested"], "Untested spotlight (top 10)"))
	print()
	print(format_increases(report["increase_events"]))
	print()
	for stat in suggest_extra_stats(report):
		print(f"- {stat}")


def main() -> int:
	args = parse_args()
	report = build_report(args.year, args.root)
	print_report(args.year, report)
	return 0


if __name__ == "__main__":
	sys.exit(main())
