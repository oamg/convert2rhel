import json
import os

import jsonschema


def _load_json_schema(path):
    """Load the JSON schema from the system."""
    assert os.path.exists(path)

    # Python2 doesn't have the nice `with` syntax.
    handler = open(path, "r")
    data = json.load(handler)
    handler.close()
    return data


C2R_MIGRATION_RESULTS_SCHEMA = _load_json_schema(path="artifacts/c2r_migration_results_schema.json")
C2R_RHSM_CUSTOM_FACTS_SCHEMA = _load_json_schema(path="artifacts/c2r_facts_schema.json")

C2R_MIGRATION_RESULTS = "/etc/migration-results"
C2R_RHSM_CUSTOM_FACTS = "/etc/rhsm/facts/convert2rhel.facts"


def test_flag_system_as_converted(shell):
    """Test if the breadcrumbs file was created and corresponds to the JSON schema."""

    # We need to skip check for collected rhsm custom facts after the conversion
    # due to disabled submgr, thus adding envar
    submgr_disabled_var = "SUBMGR_DISABLED_SKIP_CHECK_RHSM_CUSTOM_FACTS=1"
    query = shell(f"set | grep {submgr_disabled_var}").output

    assert os.path.exists(C2R_MIGRATION_RESULTS)

    with open(C2R_MIGRATION_RESULTS, "r") as data:
        data_json = json.load(data)
        # If some difference between generated json and its schema invoke exception
        try:
            jsonschema.validate(instance=data_json, schema=C2R_MIGRATION_RESULTS_SCHEMA)
        except Exception:
            print(data_json)
            raise

    if submgr_disabled_var not in query:
        assert os.path.exists(C2R_RHSM_CUSTOM_FACTS)

        with open(C2R_RHSM_CUSTOM_FACTS, "r") as data:
            data_json = json.load(data)
            # If some difference between generated json and its schema invoke exception
            try:
                jsonschema.validate(instance=data_json, schema=C2R_RHSM_CUSTOM_FACTS_SCHEMA)
            except Exception:
                print(data_json)
                raise
