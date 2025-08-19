Of course. A good `README.md` is essential for making a tool usable and maintainable. Here is a comprehensive README file for the script we've built.

You can save this content directly into a file named `README.md` in the same directory as your script.

---

# Jenkins Pytest Log Analyzer

A powerful and highly customizable Python script designed to analyze pytest execution logs from Jenkins builds. It fetches logs directly from the Jenkins API, intelligently parses test results, and generates concise, actionable summary reports.

This tool is built for modern CI/CD pipelines where tests are run in parallel, flaky tests are automatically re-run, and differentiating between test failures and environment failures is critical.

## Features

-   **Multi-Job/Build Processing**: Analyze multiple Jenkins jobs, builds, and stages in a single run using a simple JSON configuration.
-   **Robust Stage Targeting**: Uses stable **Stage IDs** to fetch logs, avoiding issues with changing stage names.
-   **Parallel/Chunked Stage Support**: Automatically fetches logs from all parallel execution nodes within a stage and aggregates the results into a single report.
-   **Intelligent Rerun Handling**: Correctly identifies when a flaky test fails and then passes on a rerun, ensuring it is counted as a `PASSED` test in the final summary.
-   **Custom Stage Failure Detection**: Differentiates between test failures and critical environment/script errors (e.g., dependency installation failures, network timeouts). You can define your own error patterns in a separate config file.
-   **Detailed Failure Summaries**:
    -   Extracts test case IDs from test function names (e.g., `test_tc123_...`).
    -   Reports the exact line of code where an assertion failed.
    -   Recognizes and reports special failure types, like Applitools visual test URLs.
-   **Secure**: Uses Jenkins API Tokens via environment variables, never requiring you to hardcode credentials.
-   **Highly Maintainable**: Built with a modular, class-based structure that separates concerns (fetching, parsing, reporting), making future changes easy.

## Requirements

-   **Python 3.6+**
-   **`requests` library**:
    ```bash
    pip install requests
    ```

## Configuration

Before running the script, you need to set up three things:

### 1. Environment Variables

The script requires your Jenkins credentials to be set as environment variables for security.

-   **`JENKINS_USER`**: Your Jenkins username.
-   **`JENKINS_TOKEN`**: Your Jenkins API Token (not your password).
    -   *To get a token: In Jenkins, go to `Your Username` > `Configure` > `API Token` > `Add new Token`.*

**On Linux/macOS:**
```bash
export JENKINS_USER='your_username'
export JENKINS_TOKEN='your_api_token'
```

**On Windows (Command Prompt):**
```bash
set JENKINS_USER="your_username"
set JENKINS_TOKEN="your_api_token"
```

### 2. Job Configuration (`jobs_config.json`)

Create a JSON file (e.g., `jobs_config.json`) to define which builds the script should analyze. This file should contain a list of target objects.

**`jobs_config.json` Example:**
```json
[
  {
    "job_name": "MyProject/main",
    "build_id": "152",
    "stage_id": "27"
  },
  {
    "job_name": "AnotherProject/develop",
    "build_id": "lastSuccessfulBuild",
    "stage_id": "18"
  },
  {
    "job_name": "Legacy-System-CI",
    "build_id": "99",
    "stage_id": null
  }
]
```
-   `job_name`: The full path to the Jenkins job.
-   `build_id`: The build number (e.g., `"152"`) or an identifier like `"lastSuccessfulBuild"`.
-   `stage_id`: The numeric ID of the stage to analyze. **Set to `null` or omit the key to analyze the entire build log.**

> **How to find the Stage ID?**
> The easiest way is to use the Blue Ocean UI. Navigate to the build and click on the stage. The last number in the URL is the Stage ID (e.g., `.../pipeline/27`).

### 3. Error Patterns (`error_patterns.json`)

Create a JSON file (e.g., `error_patterns.json`) to define custom error patterns that should cause the stage to be marked as an "Environment Failure".

**`error_patterns.json` Example:**
```json
[
  {
    "pattern": "ERROR: Could not find a version that satisfies the requirement",
    "description": "Dependency Installation Failure: A required Python package could not be installed via pip."
  },
  {
    "pattern": "docker(?:-compose)?: command not found",
    "description": "Environment Setup Failure: The Docker command is not available on the execution agent."
  },
  {
    "pattern": "Could not resolve host: .*",
    "description": "Network Connectivity Error: A network request failed."
  }
]
```
-   `pattern`: A regular expression to search for in the logs.
-   `description`: A human-readable summary of the error.

## How to Use

Run the script from your terminal, providing the Jenkins URL and the path to your job configuration file.

```bash
python log_analyzer.py <jenkins_url> <path_to_jobs_config.json>
```

**Examples:**
```bash
# Analyze jobs defined in jobs_config.json
python log_analyzer.py http://jenkins.mycompany.com/ jobs_config.json

# Specify a custom path for the error patterns file
python log_analyzer.py http://jenkins.mycompany.com/ jobs_config.json --error-patterns /path/to/custom_errors.json
```

## Understanding the Output

The script produces clear, distinct reports for different outcomes.

#### Example 1: Report with Mixed Test Failures
```
================================================================================
PYTEST ANALYSIS REPORT
Context: Job: MyProject/main | Build: 152 | Stage ID: 27
================================================================================

Execution Summary (Aggregated & Rerun-Adjusted):
  - Total Tests Executed: 25
  - Passed:   23
  - Failed:   2
  - Errors:   0
  - Skipped:  0
--------------------------------------------------------------------------------

Final Failure Summary (Unique & Non-Rerun Failures):
  - TC123 : assert data['status'] == 'complete'
  - TC456 : https://eyes.applitools.com/app/test-results/some-long-id-string
================================================================================
```

#### Example 2: Report for a Stage Failure (Non-Test Error)
```
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
STAGE FAILURE REPORT
Context: Job: MyProject/main | Build: 150 | Stage ID: 25
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

Reason: Dependency Installation Failure: A required Python package could not be installed via pip.
Log Evidence: "ERROR: Could not find a version that satisfies the requirement some-package==9.9.9"

Note: Pytest analysis was skipped because a critical stage error was detected.
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
```

#### Example 3: Report when a Flaky Test Passes on Rerun
Even if `test_tc789` failed initially, it will **not** appear in the final failure summary because it eventually passed.
```
================================================================================
PYTEST ANALYSIS REPORT
Context: Job: MyProject/main | Build: 153 | Stage ID: 28
================================================================================

Execution Summary (Aggregated & Rerun-Adjusted):
  - Total Tests Executed: 25
  - Passed:   24
  - Failed:   1
  - Errors:   0
  - Skipped:  0
--------------------------------------------------------------------------------

Final Failure Summary (Unique & Non-Rerun Failures):
  - TC101 : assert result is not None
================================================================================
```

## Customization

The script is designed to be easily adapted without major code changes.

-   **Test Case ID Format**: To change how Test Case IDs are identified, modify the `test_id_pattern` regular expression inside the `PytestLogParser` class. The default is `r'(tc[-_]?\d+)'`.
-   **Applitools URL Format**: To support a different visual testing tool or a self-hosted Applitools domain, modify the `applitools_pattern` regex inside the `PytestLogParser` class.

## Troubleshooting

-   **Authentication Error (401/403)**: Check that your `JENKINS_USER` and `JENKINS_TOKEN` environment variables are set correctly and that the token is valid.
-   **Stage ID Not Found**: Verify the Stage ID is correct for the specified build. Use the Blue Ocean UI to find the exact ID.
-   **No Pytest Tests Found**:
    -   Ensure the correct Stage ID is being targeted.
    -   Confirm that pytest is actually running and producing its standard summary output in the logs.
    -   For rerun detection to work, pytest must be run in **verbose mode (`-v`)** so that `PASSED` statuses are explicitly logged.
