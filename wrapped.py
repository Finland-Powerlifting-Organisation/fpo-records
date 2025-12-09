#!/usr/bin/env python3

import argparse
import csv
import re
import sys
from collections import Counter
from datetime import date
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
	previous_date: date
	current_date: date
	previous_has_exact_date: bool
	previous_source_file: str
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


def make_date(year: int, month: int, day: int) -> date:
	month = month if month else 1
	day = day if day else 1
	return date(year, month, day)


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


def is_open_division(key: str) -> bool:
	parts = key.split("|")
	if len(parts) < 2:
		return False
	return parts[1] in {"Open", "Open-D"}


def build_report(target_year: int, root: Path) -> Dict[str, object]:
	records: Dict[str, Tuple[float, date, str, bool]] = {}
	total_broken = 0
	new_records = 0
	location_counts: Counter[str] = Counter()
	name_counts: Counter[str] = Counter()
	name_counts_untested: Counter[str] = Counter()
	name_counts_tested: Counter[str] = Counter()
	increase_events: List[IncreaseEvent] = []
	open_increase_events: List[IncreaseEvent] = []
	name_increase_totals: Counter[str] = Counter()
	total_increase = 0.0
	files = sorted_event_files(root)

	for (year, month, day), path in files:
		current_date = make_date(year, month, day)
		current_has_exact_date = bool(month and day)
		for row in read_rows(path):
			prev_record = records.get(row.key)
			prev_weight = prev_record[0] if prev_record else None
			prev_date = prev_record[1] if prev_record else None
			prev_source_file = prev_record[2] if prev_record else ""
			prev_has_exact_date = prev_record[3] if prev_record else False
			is_new_best = prev_weight is None or row.weight > prev_weight
			if is_new_best and year == target_year:
				total_broken += 1
				location_counts[row.location] += 1
				name_counts[row.name] += 1
				if is_tested(row.key):
					name_counts_tested[row.name] += 1
				if not is_tested(row.key):
					name_counts_untested[row.name] += 1
				if prev_weight is None:
					new_records += 1
				else:
					delta = row.weight - prev_weight
					total_increase += delta
					name_increase_totals[row.name] += delta
					increase_events.append(
						IncreaseEvent(
							name=row.name,
							key=row.key,
							location=row.location,
							previous=prev_weight,
							new=row.weight,
							delta=delta,
							previous_date=prev_date or current_date,
							current_date=current_date,
							previous_has_exact_date=prev_has_exact_date,
							previous_source_file=prev_source_file,
							source_file=path.name,
						)
					)
					if is_open_division(row.key):
						open_increase_events.append(
							IncreaseEvent(
								name=row.name,
								key=row.key,
								location=row.location,
								previous=prev_weight,
								new=row.weight,
								delta=delta,
								previous_date=prev_date or current_date,
								current_date=current_date,
								previous_has_exact_date=prev_has_exact_date,
								previous_source_file=prev_source_file,
								source_file=path.name,
							)
						)
			if is_new_best:
				records[row.key] = (row.weight, current_date, path.name, current_has_exact_date)

	return {
		"total_broken": total_broken,
		"new_records": new_records,
		"location_counts": location_counts,
		"name_counts": name_counts,
		"name_counts_untested": name_counts_untested,
		"name_counts_tested": name_counts_tested,
		"increase_events": increase_events,
		"open_increase_events": open_increase_events,
		"name_increase_totals": name_increase_totals,
		"total_increase": total_increase,
	}


def format_counter(counter: Counter[str], title: str, limit: int = 20) -> str:
	lines = [title]
	for idx, (name, count) in enumerate(counter.most_common(limit), start=1):
		lines.append(f"{idx:2d}. {name} — {count}")
	if len(lines) == 1:
		lines.append("   (no data)")
	return "\n".join(lines)


def format_weight_counter(counter: Counter[str], title: str, limit: int = 10) -> str:
	lines = [title]
	for idx, (name, total) in enumerate(counter.most_common(limit), start=1):
		lines.append(f"{idx:2d}. {name} — {total:.1f} kg")
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


def format_open_glowups(events: List[IncreaseEvent], limit: int = 10) -> str:
	if not events:
		return "Open division glow-ups (no qualifying improvements)"
	sorted_events = sorted(
		events,
		key=lambda item: (item.delta, item.new, item.name),
		reverse=True,
	)
	lines = ["Open division glow-ups (tested + untested, excluding brand new records)"]
	for idx, event in enumerate(sorted_events[:limit], start=1):
		lines.append(
			f"{idx:2d}. {event.name} ({event.key}) +{event.delta:.1f} "
			f"→ {event.new:.1f} at {event.location} [{event.source_file}]"
		)
	return "\n".join(lines)


def format_percent_glowups(events: List[IncreaseEvent], limit: int = 10) -> str:
	lines = ["Biggest glow-ups by % (excluding brand new records)"]
	percent_events = [
		(
			(event.delta / event.previous * 100) if event.previous > 0 else 0.0,
			event,
		)
		for event in events
		if event.previous > 0
	]
	if not percent_events:
		lines.append("   (no data)")
		return "\n".join(lines)
	sorted_events = sorted(
		percent_events,
		key=lambda item: (item[0], item[1].new, item[1].name),
		reverse=True,
	)
	for idx, (pct, event) in enumerate(sorted_events[:limit], start=1):
		lines.append(
			f"{idx:2d}. {event.name} ({event.key}) +{pct:.1f}% "
			f"→ {event.new:.1f} at {event.location} [{event.source_file}]"
		)
	return "\n".join(lines)


def format_percent_open_glowups(events: List[IncreaseEvent], limit: int = 10) -> str:
	lines = ["Open division glow-ups by % (tested + untested, excluding brand new records)"]
	percent_events = [
		(
			(event.delta / event.previous * 100) if event.previous > 0 else 0.0,
			event,
		)
		for event in events
		if event.previous > 0
	]
	if not percent_events:
		lines.append("   (no data)")
		return "\n".join(lines)
	sorted_events = sorted(
		percent_events,
		key=lambda item: (item[0], item[1].new, item[1].name),
		reverse=True,
	)
	for idx, (pct, event) in enumerate(sorted_events[:limit], start=1):
		lines.append(
			f"{idx:2d}. {event.name} ({event.key}) +{pct:.1f}% "
			f"→ {event.new:.1f} at {event.location} [{event.source_file}]"
		)
	return "\n".join(lines)


def format_oldest_broken(events: List[IncreaseEvent], limit: int = 10) -> str:
	lines = ["Oldest records finally broken"]
	age_events = []
	for event in events:
		if event.previous_date:
			age_days = (event.current_date - event.previous_date).days
			age_events.append((age_days, event))
	if not age_events:
		lines.append("   (no data)")
		return "\n".join(lines)
	sorted_events = sorted(
		age_events,
		key=lambda item: (item[0], item[1].new, item[1].name),
		reverse=True,
	)
	for idx, (age_days, event) in enumerate(sorted_events[:limit], start=1):
		if event.previous_has_exact_date:
			age_text = f"{age_days} days"
		else:
			age_years = event.current_date.year - event.previous_date.year
			age_text = f"{age_years} years"
		lines.append(
			f"{idx:2d}. {event.name} ({event.key}) after {age_text} "
			f"→ {event.new:.1f} at {event.location} [{event.source_file}] "
			f"(set on {event.previous_date.isoformat()} via {event.previous_source_file})"
		)
	return "\n".join(lines)


def suggest_extra_stats(report: Dict[str, object]) -> List[str]:
	total_broken = report["total_broken"]
	new_records = report["new_records"]
	unique_people = len(report["name_counts"])
	extra = [
		f"Fresh records set from scratch: {new_records}",
		f"Distinct lifters hitting the board: {unique_people}",
	]
	return extra


def print_report(year: int, report: Dict[str, object]) -> None:
	print(f"FPO Records Wrapped {year}")
	print("=" * 40)
	print(f"Records broken (all divisions): {report['total_broken']}")
	print(f"Total kg added to existing records: {report['total_increase']:.1f} kg")
	for stat in suggest_extra_stats(report):
		print(stat)
	print()
	print(format_counter(report["location_counts"], "Where the magic happened (top 10)"))
	print()
	print(format_counter(report["name_counts"], "All-time hitters (tested + untested, top 10)"))
	print()
	print(format_counter(report["name_counts_tested"], "Record rake (tested only, top 10)"))
	print()
	print(format_counter(report["name_counts_untested"], "Untested spotlight (top 10)"))
	print()
	print(format_increases(report["increase_events"]))
	print()
	print(format_open_glowups(report["open_increase_events"]))
	print()
	print(format_percent_glowups(report["increase_events"]))
	print()
	print(format_percent_open_glowups(report["open_increase_events"]))
	print()
	print(format_oldest_broken(report["increase_events"]))
	print()
	print(format_weight_counter(report["name_increase_totals"], "Total kg added leaderboard (excluding brand new records)"))


def main() -> int:
	args = parse_args()
	report = build_report(args.year, args.root)
	print_report(args.year, report)
	return 0


if __name__ == "__main__":
	sys.exit(main())
