#!/usr/bin/env python3

import argparse
import csv
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


FILE_PATTERN = re.compile(r"^(\d{4})(?:-(\d{2})-(\d{2}))?\.csv$")
SEXES = ("M", "F")
MALE_CLASSES = ("52", "56", "60", "67.5", "75", "82.5", "90", "100", "110", "125", "140", "SHW")
FEMALE_CLASSES = ("44", "48", "52", "56", "60", "67.5", "75", "82.5", "90", "100", "110", "SHW")
CLASSES = tuple(dict.fromkeys(MALE_CLASSES + FEMALE_CLASSES))
DIVISIONS = ("Open", "Youth", "T13-15", "T16-17", "T18-19", "J20-23", "M40-44", "M45-49", "M50-54", "M55-59", "M60-64", "M65-69", "M70-74", "M75-79", "M80+")
LIFTS = ("S", "B", "D", "SBD")
EVENTS = ("SBD", "B", "D")
EQUIPMENT = ("Raw", "Wraps", "Sleeves", "Bare", "Single-ply", "Multi-ply", "Unlimited")


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(
		description="Check record files for unknown keys or non-increasing records.",
	)
	parser.add_argument(
		"--root",
		type=Path,
		default=Path("."),
		help="Directory containing the CSV record files (defaults to cwd).",
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


def sorted_record_files(root: Path) -> List[Tuple[Tuple[int, int, int], Path]]:
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


def valid_keyset() -> set[str]:
	keys: set[str] = set()
	divisions_add_tested = tuple({*DIVISIONS, *(f"{div}-D" for div in DIVISIONS)})

	for sex in SEXES:
		weight_classes = MALE_CLASSES if sex == "M" else FEMALE_CLASSES
		for division in divisions_add_tested:
			for event in EVENTS:
				for lift in LIFTS:
					valid_lift = (lift == "B" and event == "B") or (lift == "D" and event == "D") or event == "SBD"
					if not valid_lift:
						continue
					for eq in EQUIPMENT:
						if eq == "Unlimited" and not (event == "B" and lift == "B"):
							continue
						invalid_bench_dead_eq = (lift in ("B", "D")) and (eq in ("Bare", "Sleeves", "Wraps"))
						invalid_squat_total_eq = (lift in ("S", "SBD")) and (eq == "Raw")
						if invalid_bench_dead_eq or invalid_squat_total_eq:
							continue
						for weight in weight_classes:
							keys.add(f"{sex}|{division}|{event}|{eq}|{weight}|{lift}")
	return keys


def read_rows(path: Path) -> Iterable[Tuple[int, str, float, str]]:
	with path.open(newline="", encoding="utf-8") as handle:
		reader = csv.reader(handle)
		for idx, row in enumerate(reader, start=1):
			if not row or len(row) < 2:
				continue
			key = row[0].strip()
			if not key:
				continue
			try:
				weight = float(row[1])
			except ValueError:
				print(f"⚠️  Skipping row with invalid weight in {path.name}:{idx}: {row[1]!r}")
				continue
			name = row[2].strip() if len(row) > 2 else ""
			yield idx, key, weight, name


def check_files(files: List[Tuple[Tuple[int, int, int], Path]]) -> List[str]:
	warnings: List[str] = []
	records: Dict[str, Tuple[float, str]] = {}
	known_keys = valid_keyset()

	if not files:
		warnings.append("⚠️  No CSV files matching pattern YYYY.csv or YYYY-MM-DD.csv were found.")
		return warnings

	for _file_index, (_date, path) in enumerate(files):
		for line_no, key, weight, name in read_rows(path):
			if key not in known_keys:
				name_suffix = f" ({name})" if name else ""
				warnings.append(
					f"⚠️  Unrecognized key '{key}' in {path.name}:{line_no}{name_suffix}"
				)
			if key not in records:
				records[key] = (weight, path.name)
				continue

			prev_weight, prev_source = records[key]
			if weight <= prev_weight:
				warnings.append(
					f"⚠️  Non-increasing record for '{key}' in {path.name}:{line_no}: "
					f"{weight} <= {prev_weight} (last set in {prev_source})"
				)
			else:
				records[key] = (weight, path.name)

	return warnings


def main() -> int:
	args = parse_args()
	files = sorted_record_files(args.root)
	warnings = check_files(files)

	if warnings:
		for warning in warnings:
			print(warning)
		print(f"⚠️  Finished with {len(warnings)} warning(s).")
	else:
		print(f"✅ Checked {len(files)} file(s); no issues found.")

	return 0


if __name__ == "__main__":
	sys.exit(main())
