import os
import re
import json
import argparse
import requests
from typing import Dict, Any, Optional, List, Set, Tuple

# --- Configuration ---
JENKINS_USER = os.getenv("JENKINS_USER")
JENKINS_TOKEN = os.getenv("JENKINS_TOKEN")

# --- JenkinsLogFetcher & PytestLogParser (no changes) ---
# ... (These classes are identical to the previous version)
class JenkinsLogFetcher:
    def __init__(self, jenkins_url: str, job_name: str, build_id: str):
        if not jenkins_url.endswith('/'): jenkins_url += '/'
        self.base_url = jenkins_url; self.job_name = job_name; self.build_id = build_id
        self.session = requests.Session()
        if JENKINS_USER and JENKINS_TOKEN: self.session.auth = (JENKINS_USER, JENKINS_TOKEN)
        else: print("Warning: JENKINS_USER or JENKINS_TOKEN not set.")
    def get_log(self, stage_id: Optional[str] = None) -> str:
        if stage_id: return self._get_log_for_stage_id(stage_id)
        else:
            log_url = f"{self.base_url}job/{self.job_name}/{self.build_id}/consoleText"
            return self._fetch_url_content(log_url)
    def _fetch_url_content(self, url: str) -> str:
        try:
            response = self.session.get(url, timeout=30); response.raise_for_status()
            return response.text
        except requests.exceptions.RequestException as e: raise Exception(f"Failed to fetch from {url}. Error: {e}") from e
    def _get_log_for_stage_id(self, stage_id: str) -> str:
        wfapi_url = f"{self.base_url}job/{self.job_name}/{self.build_id}/wfapi/describe"
        build_structure = json.loads(self._fetch_url_content(wfapi_url))
        node_ids = [node.get("id") for stage in build_structure.get("stages", []) if stage.get("id") == stage_id for node in stage.get("stageFlowNodes", []) if node.get("id")]
        if not node_ids: raise ValueError(f"No execution nodes for Stage ID '{stage_id}'.")
        print(f"Found {len(node_ids)} execution node(s) for Stage ID '{stage_id}'. Fetching logs...")
        all_logs = [self._fetch_url_content(f"{self.base_url}job/{self.job_name}/{self.build_id}/execution/node/{node_id}/log/") for node_id in node_ids]
        return "\n".join(all_logs)

class PytestLogParser:
    def __init__(self, log_content: str):
        self.log = log_content
        self.results = {"total": 0, "passed": 0, "failed": 0, "errors": 0, "skipped": 0, "failures": []}
        self.test_id_pattern = re.compile(r'(tc[-_]?\d+)', re.IGNORECASE)
    def parse(self) -> Dict[str, Any]:
        self._parse_summary()
        self._parse_failure_details()
        return self.results
    def _parse_summary(self):
        summary_pattern = re.compile(r"={10,}\s(.*?)\s={10,}")
        for key in ["passed", "failed", "errors", "skipped", "total"]: self.results[key] = 0
        found = False
        for match in summary_pattern.finditer(self.log):
            found = True; summary_text = match.group(1)
            counts = {"failed": r"(\d+)\s+failed", "passed": r"(\d+)\s+passed", "errors": r"(\d+)\s+error", "skipped": r"(\d+)\s+skipped"}
            for key, pattern in counts.items():
                if m := re.search(pattern, summary_text): self.results[key] += int(m.group(1))
        if not found: print("Warning: No Pytest summary lines found.")
        self.results["total"] = sum(self.results[key] for key in ["passed", "failed", "errors", "skipped"])
    def _get_passed_test_ids(self) -> Set[str]:
        passed_ids = set()
        passed_pattern = re.compile(r"^(?:.*\s)?(\S+\.py::\S+)\s+PASSED", re.MULTILINE)
        for match in passed_pattern.finditer(self.log):
            test_name = match.group(1)
            if m := self.test_id_pattern.search(test_name): passed_ids.add(m.group(1).upper())
            else: passed_ids.add(test_name)
        return passed_ids
    def _parse_failure_details(self):
        passed_ids = self._get_passed_test_ids()
        if passed_ids: print(f"Found {len(passed_ids)} unique passed tests. Rerun failures for these will be ignored.")
        seen_failures = set(); applitools_pattern = re.compile(r'(https?://\S+\.applitools\.com\S+)')
        failure_block_pattern = re.compile(r"_{5,}\s+(test_\S+)\s+_{5,}(.*?)(?=(?:_{5,}\s+test_\S+\s+_{5,}|={10,}))", re.DOTALL)
        error_line_pattern = re.compile(r"^\s*(\S+\.py):(\d+):\s+(.*Error.*)$", re.MULTILINE)
        for match in failure_block_pattern.finditer(self.log):
            test_name, failure_content = match.group(1), match.group(2)
            test_id = (m.group(1).upper() if (m := self.test_id_pattern.search(test_name)) else test_name)
            if test_id in passed_ids: continue
            failure_detail = "Could not determine failure."
            if applitools_match := applitools_pattern.search(failure_content): failure_detail = applitools_match.group(1)
            elif error_line_match := error_line_pattern.search(failure_content):
                _, line_number, error_type = error_line_match.groups()
                failure_detail = f"Error: {error_type}"
                if code_match := re.compile(rf"^{line_number}\s+>\s+(.*)$", re.MULTILINE).search(failure_content):
                    failure_detail = code_match.group(1).strip()
            if (test_id, failure_detail) not in seen_failures:
                self.results["failures"].append({"test_id": test_id, "code_line": failure_detail})
                seen_failures.add((test_id, failure_detail))

# --- ReportGenerator (no changes) ---
class ReportGenerator:
    def __init__(self, results: Dict[str, Any], header: Optional[str] = None):
        self.results = results; self.header = header
    def print_report(self):
        print("\n" + "="*80); print("PYTEST ANALYSIS REPORT")
        if self.header: print(f"Context: {self.header}")
        print("="*80)
        if self.results["total"] == 0: print("No pytest tests were found."); print("="*80 + "\n"); return
        print(f"\nExecution Summary (Aggregated & Rerun-Adjusted):")
        print(f"  - Total Tests Executed: {self.results['total']}"); print(f"  - Passed:   {self.results['passed']}"); print(f"  - Failed:   {self.results['failed']}"); print(f"  - Errors:   {self.results['errors']}"); print(f"  - Skipped:  {self.results['skipped']}")
        print("-" * 80)
        if not self.results["failures"]: print("\nResult: All Testcases are passed in the Jenkins.")
        else:
            print("\nFinal Failure Summary (Unique & Non-Rerun Failures):")
            for failure in self.results["failures"]: print(f"  - {failure['test_id']} : {failure['code_line']}")
        print("="*80 + "\n")

# --- NEW Class to Detect Stage-Level Failures ---
class StageFailureDetector:
    """
    Scans logs for a predefined set of critical, non-test-related errors.
    """
    def __init__(self, patterns_path: str):
        self.patterns = self._load_patterns(patterns_path)

    def _load_patterns(self, path: str) -> List[Dict[str, Any]]:
        try:
            with open(path, 'r') as f:
                patterns_data = json.load(f)
            # Pre-compile regexes for efficiency
            for p in patterns_data:
                p['compiled'] = re.compile(p['pattern'], re.IGNORECASE)
            return patterns_data
        except FileNotFoundError:
            print(f"Warning: Error patterns file not found at '{path}'. Stage failure detection is disabled.")
            return []
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Warning: Error parsing patterns file '{path}': {e}. Stage failure detection is disabled.")
            return []

    def check(self, log_content: str) -> Optional[Tuple[str, str]]:
        """
        Checks log content against the patterns. Returns description and matched line if found.
        """
        for p in self.patterns:
            match = p['compiled'].search(log_content)
            if match:
                # Return the description and the first line of the matched text
                matched_line = match.group(0).strip().split('\n')[0]
                return p['description'], matched_line
        return None

# --- MultiJobAnalyzer (MODIFIED to use the new detector) ---
class MultiJobAnalyzer:
    def __init__(self, jenkins_url: str, config_path: str, error_patterns_path: str):
        self.jenkins_url = jenkins_url
        self.targets = self._load_config(config_path)
        # *** NEW: Initialize the failure detector ***
        self.failure_detector = StageFailureDetector(error_patterns_path)

    def _load_config(self, config_path: str) -> List[Dict[str, str]]:
        # ... (no change)
        try:
            with open(config_path, 'r') as f: data = json.load(f)
            if not isinstance(data, list): raise ValueError("Config file must be a JSON list.")
            return data
        except FileNotFoundError: raise FileNotFoundError(f"Error: Config file not found at '{config_path}'")
        except json.JSONDecodeError: raise ValueError(f"Error: Could not decode JSON from '{config_path}'.")

    def run_all(self):
        if not self.targets: print("No analysis targets found."); return
        for i, target in enumerate(self.targets, 1):
            header_context = f"Job: {target.get('job_name')} | Build: {target.get('build_id')} | Stage ID: {target.get('stage_id') or 'Full Log'}"
            print(f"--- Analyzing Target {i}/{len(self.targets)}: {header_context} ---")
            
            job_name, build_id = target.get("job_name"), target.get("build_id")
            if not job_name or not build_id:
                print(f"Skipping invalid target: {target}."); continue
            
            try:
                # 1. Fetch Logs
                fetcher = JenkinsLogFetcher(self.jenkins_url, job_name, build_id)
                log_content = fetcher.get_log(stage_id=target.get("stage_id"))
                
                # 2. *** NEW: Check for Stage-Level Failures FIRST ***
                stage_failure = self.failure_detector.check(log_content)
                if stage_failure:
                    description, matched_line = stage_failure
                    self._print_stage_failure_report(header_context, description, matched_line)
                    continue # Skip to the next target

                # 3. If no stage failure, proceed with Pytest Analysis
                parser = PytestLogParser(log_content)
                analysis_results = parser.parse()
                
                reporter = ReportGenerator(analysis_results, header=header_context)
                reporter.print_report()

            except Exception as e:
                print(f"!!! ERROR processing target {job_name}/{build_id}: {e}\n")
    
    def _print_stage_failure_report(self, header: str, description: str, matched_line: str):
        """Prints a standardized report for non-test failures."""
        print("\n" + "!"*80)
        print("STAGE FAILURE REPORT")
        print(f"Context: {header}")
        print("!"*80)
        print(f"\nReason: {description}")
        print(f"Log Evidence: \"{matched_line}\"")
        print("\nNote: Pytest analysis was skipped because a critical stage error was detected.")
        print("!"*80 + "\n")

# --- Main Execution Block (MODIFIED to accept new config path) ---
def main():
    parser = argparse.ArgumentParser(description="Analyze logs from Jenkins builds for Pytest results or stage failures.")
    parser.add_argument("jenkins_url", help="Base URL of your Jenkins instance.")
    parser.add_argument("config_file", help="Path to the JSON job configuration file.")
    # *** NEW: Optional argument for the error patterns file ***
    parser.add_argument(
        "--error-patterns",
        default="error_patterns.json",
        help="Path to the JSON file with stage failure patterns (default: error_patterns.json)."
    )
    args = parser.parse_args()

    if not JENKINS_USER or not JENKINS_TOKEN:
        print("Error: JENKINS_USER and JENKINS_TOKEN environment variables must be set.")
        return

    try:
        analyzer = MultiJobAnalyzer(args.jenkins_url, args.config_file, args.error_patterns)
        analyzer.run_all()
    except Exception as e:
        print(f"\nA critical error occurred: {e}")

if __name__ == "__main__":
    main()