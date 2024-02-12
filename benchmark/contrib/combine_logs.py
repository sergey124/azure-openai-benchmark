import argparse
import json
import logging
import matplotlib.pyplot as plt
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd


def plot(df):
    df.replace('n/a', np.nan, inplace=True)
    df = df.apply(pd.to_numeric, errors='ignore')
    df['failure_rate'] = (df['failures'] / df['requests']) * 100

    # Plotting the data
    plt.figure(figsize=(10, 6))

    # Plotting rpm
    plt.plot(df['rate'], df['rpm'], marker='o', label='RPM', color='blue')

    # Plotting failure rate
    plt.plot(df['rate'], df['failure_rate'], marker='o', label='Failure Rate (%)', color='red')

    # Adding labels and title
    plt.xlabel('Request rate per minute')
    plt.ylabel('Count')
    plt.title('Rate vs. RPM, Requests, Failure Rate')
    plt.xticks(df['rate'])  # Ensure all rate values are displayed on x-axis
    plt.grid(True)
    plt.legend()

    # Saving the visualization to a file
    plt.savefig('rate_vs_metrics_with_failure_rate.png')

    # Displaying the plot
    plt.show()


def combine_logs_to_csv(
    args: argparse.Namespace,
) -> None:
    """
    Combines all logs in a directory into a single csv file.

    Args:
        log_dir: Directory containing the log files.
        save_path: Path to save the output output CSV.
        load_recursive: Whether to load logs in all subdirectories of log_dir.
            Defaults to True.
    """
    log_dir = args.source_dir
    save_path = args.save_path
    load_recursive = args.load_recursive

    log_dir = Path(log_dir)
    log_files = log_dir.rglob("*.log") if load_recursive else log_dir.glob("*.log")
    log_files = sorted(log_files)
    # Extract run info from each log file
    run_summaries = [extract_run_info_from_log_path(log_file) for log_file in log_files]
    run_summaries = [summary for summary in run_summaries if isinstance(summary, dict)]
    # Convert to dataframe and save to csv
    if run_summaries:
        df = pd.DataFrame(run_summaries)
        df.set_index("filename", inplace=True)
        df.to_csv(save_path, index=True, sep=';')
        logging.info(f"Saved {len(df)} runs to {save_path}")

        plot(df)
    else:
        logging.error(f"No valid runs found in {log_dir}")
    return


def extract_run_info_from_log_path(log_file: str) -> Optional[dict]:
    """Extracts run info from log file path"""
    run_args = None
    last_logged_stats = None
    early_terminated = False
    lines_since_request_draining = 0
    # Process lines, including only info BEFORE early termination (for terminated sessions), or the final log AFFTER requests start to drain (for valid sessions)
    with open(log_file) as f:
        for line in f.readlines():
            if "got terminate signal" in line:
                # Ignore any stats after termination or draining of requests (since RPM, TPM, rate etc will start to decline as requests gradually finish)
                break
            # Save most recent line
            if "Load" in line:
                run_args = json.loads(line.split("Load test args: ")[-1])
            if "run_seconds" in line:
                last_logged_stats = line
            if lines_since_request_draining == 1:
                # Previous line was draining, use this line as the last set of valid stats
                break
            if "requests to drain" in line:
                # Current line is draining, next line is the last set of valid stats. Allow one more line to be processed.
                lines_since_request_draining += 1
    if not run_args:
        logging.error(
            f"Could not extract run args from log file {log_file} - missing run info (it might have been generated with a previous code version)."
        )
        return None
    run_args["early_terminated"] = early_terminated
    run_args["filename"] = Path(log_file).name
    # Extract last line of valid stats from log if available
    if last_logged_stats:
        last_logged_stats = flatten_dict(json.loads(last_logged_stats))
        run_args.update(last_logged_stats)
        run_args["run_has_non_throttled_failures"] = (
            int(run_args["failures"]) - int(run_args["throttled"]) > 0
        )
    return run_args


def flatten_dict(input: dict) -> dict:
    """
    Flattens dictionary of nested dictionaries/lists into a single level dictionary
    Taken from https://www.geeksforgeeks.org/flattening-json-objects-in-python/
    """
    out = {}

    def flatten(x, name=""):
        # If the Nested key-value
        # pair is of dict type
        if isinstance(x, dict):
            for a in x:
                flatten(x[a], name + a + "_")

        # If the Nested key-value
        # pair is of list type
        elif isinstance(x, dict):
            i = 0
            for a in x:
                flatten(a, name + str(i) + "_")
                i += 1
        else:
            out[name[:-1]] = x

    flatten(input)
    return out


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def main():
    parser = argparse.ArgumentParser(
        description="CLI for combining existing log files."
    )
    parser.add_argument(
        "source_dir", type=str, help="Directory containing the log files."
    )
    parser.add_argument(
        "save_path", type=str, help="Path to save the output output CSV."
    )
    parser.add_argument(
        "--load-recursive",
        action="store_true",
        help="Whether to load logs in all subdirectories of log_dir.",
    )

    args = parser.parse_args()
    combine_logs_to_csv(args)


main()
