import jsonschema

from conftest import _load_json_schema


C2R_MIGRATION_RESULTS_SCHEMA = _load_json_schema(path="artifacts/c2r_migration_results_schema.json")
C2R_RHSM_CUSTOM_FACTS_SCHEMA = _load_json_schema(path="artifacts/c2r_facts_schema.json")

C2R_MIGRATION_RESULTS = "/etc/migration-results"
C2R_RHSM_CUSTOM_FACTS = "/etc/rhsm/facts/convert2rhel.facts"


def test_flag_system_as_converted(shell):
    """
    Verify, that the breadcrumbs file was created and corresponds to the JSON schema after the conversion.
    """

    submgr_disabled_var = "SUBMGR_DISABLED_SKIP_CHECK_RHSM_CUSTOM_FACTS=1"
    query = shell(f"set | grep {submgr_disabled_var}").output

    data_json = _load_json_schema(C2R_MIGRATION_RESULTS)

    # If some difference between generated json and its schema invoke exception
    try:
        jsonschema.validate(instance=data_json, schema=C2R_MIGRATION_RESULTS_SCHEMA)
    except Exception:
        print(data_json)
        raise

    # We need to validate the schema just in case the SUBMGR_DISABLED_SKIP_CHECK_RHSM_CUSTOM_FACTS
    # envar is not set (we might set the envar for example due to disabled submgr)
    if submgr_disabled_var not in query:
        data_json = _load_json_schema(C2R_RHSM_CUSTOM_FACTS)

        # If some difference between generated json and its schema invoke exception
        try:
            jsonschema.validate(instance=data_json, schema=C2R_RHSM_CUSTOM_FACTS_SCHEMA)
        except Exception:
            print(data_json)
            raise
