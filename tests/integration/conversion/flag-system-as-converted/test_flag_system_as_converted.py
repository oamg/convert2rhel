import json
import os

import jsonschema


# TODO improve import of schema
SCHEMA = '{"definitions":{},"$schema":"http://json-schema.org/draft-07/schema#","$id":"https://example.com/object1628676489.json","title":"Migrations file schema v1","type":"object","required":["activities"],"properties":{"activities":{"$id":"#root/activities","title":"Activities","type":"array","description":"A collection of all migration activities performed on this system","default":[],"items":{"$id":"#root/activities/items","description":"Migration item","type":"object","required":["activity","packages","executed","success","activity_started","activity_ended","source_os","target_os","env","run_id","version"],"properties":{"activity":{"$id":"#root/activities/items/activity","type":"string","enum":["conversion","upgrade"],"description":"Type of migration activity"},"version":{"$id":"#root/activities/items/version","type":"string","description":"Version of the activity object"},"packages":{"$id":"#root/activities/items/packages","description":"List of packages that directly facilitate the activity","type":"array","default":[],"items":{"$id":"#root/activities/items/packages/items","type":"object","required":["nevra","signature"],"properties":{"nevra":{"$id":"#root/activities/items/packages/items/nevra","description":"RPM NEVRA of the package","type":"string","examples":["leapp-0.12.0-1.el7_9.noarch"]},"signature":{"$id":"#root/activities/items/packages/items/signature","description":"RPM Signature of the package","type":"string","examples":["RSA/SHA256, Mon 29 Mar 2021 03:05:37 PM UTC, Key ID 199e2f91fd431d51"]}}}},"executed":{"$id":"#root/activities/items/executed","description":"Complete command line with which the migration activity was started","type":"string","examples":["leapp upgrade --debug"]},"success":{"$id":"#root/activities/items/success","description":"Indicates whether the migration activity completed successfully","type":"boolean","examples":[true]},"activity_started":{"$id":"#root/activities/items/activity_started","description":"ISO 8601 timestamp of when the activity was started","type":"string","examples":["202104220800Z"]},"activity_ended":{"$id":"#root/activities/items/activity_ended","description":"ISO 8601 timestamp of when the activity ended","type":"string","examples":["202104220800Z"]},"source_os":{"$id":"#root/activities/items/source_os","description":"Source operating system where the activity was started","type":"string","examples":["Red Hat Enterprise Linux 7.9"]},"target_os":{"$id":"#root/activities/items/target_os","description":"Target operating system where the migration ended","type":"string","examples":["Red Hat Enterprise Linux 8.3"]},"env":{"$id":"#root/activities/items/env","description":"List of migration specific environment variables","type":"object"},"run_id":{"$id":"#root/activities/items/run_id","description":"Connects invocation to implementation defined identifier","type":"string","examples":["a91dccab-84e8-4a28-b28e-102b073200a9"]}}}}}}'

DATA = "/etc/migration-results"


def test_flag_system_as_converted():
    """Testing if was created breadcrumbs file and corresponds with schema."""

    assert os.path.exists(DATA)

    with open(DATA, "r") as data:
        schema_json = json.loads(SCHEMA)
        data_json = json.load(data)
        # If some difference between generated json and its schema invoke exception
        jsonschema.validate(instance=data_json, schema=schema_json)
