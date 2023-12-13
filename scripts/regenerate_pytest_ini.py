#!/usr/bin/env python
import os
import re
import sys


def find_custom_markers(directories=("convert2rhel/unit_tests", "tests")):
    """
    Walk through the directories provided as a tuple in the function argument
    and look for the custom pytest markers in each .py file.
    Ignore the builtin markers by removing from the results.
    """
    markers = set()
    # Regex to match the pytest markers
    marker_pattern = re.compile(r"@pytest\.mark\.(?P<marker>\w+)\(?")

    for directory in directories:
        for root, dirs, files in os.walk(directory):
            # Exclude hidden directories, e.g., .git and venv dirs. This doesn't really
            # need to be here at this point, however might come in use if we decide to walk
            # through each directory in the project not just the two currently specified.
            dirs[:] = [d for d in dirs if not d[0] == "." and "venv" not in d]
            for file in files:
                if file.endswith(".py"):
                    file_path = os.path.join(root, file)
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                        matches = marker_pattern.findall(content)
                        markers.update(matches)

    # Exclude built-in markers
    ignored_builtin_markers = [
        "filterwarnings",
        "skip",
        "skipif",
        "xfail",
        "parametrize",
        "usefixtures",
        "tryfirst",
        "trylast",
    ]
    custom_markers = markers - set(ignored_builtin_markers)

    return custom_markers


def update_pytest_ini(custom_markers, ini_file="pytest.ini"):
    """
    Update the pytest.ini config with the custom markers.
    """

    ini_startswith = '[pytest]\ntestpaths = "convert2rhel/unit_tests"\nmarkers =\n'
    with open(ini_file, "w", encoding="utf-8") as f:
        if custom_markers:
            f.write("# Generated automatically by the regenerate-pytest-ini pre-commit hook\n\n")
            f.write(ini_startswith)
            for marker in sorted(custom_markers):
                f.write(f"    {marker}\n")


def main():
    """
    Main function to execute the regenerate-pytest-ini pre-commit hook.
    """
    custom_markers = find_custom_markers()
    if custom_markers:
        update_pytest_ini(custom_markers)
        print("pytest.ini regenerated with custom markers.")
        return 0
    else:
        print("No custom markers found.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
