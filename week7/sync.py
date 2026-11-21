
#!/usr/bin/env python3
"""WIC2005 Week 7 - Synchronize API state with intent.yaml."""

import argparse
import os
import sys
import time
import random
import uuid

import requests
import yaml
from inventory import Client

API = os.environ.get("LAB_API_URL", "http://api:8000")


def read_current_state(client):
    """Read all existing VLANs and ACL entries from the API."""

    print("\nReading current API configuration...")

    vlans, _ = client.get_all(f"{API}/api/v1/vlans")
    acl_entries, _ = client.get_all(f"{API}/api/v1/acl/entries")

    print(f"Found {len(vlans)} existing VLANs")
    print(f"Found {len(acl_entries)} existing ACL entries")

    return vlans, acl_entries


def acl_key(entry):
    """Represent an ACL rule by its meaningful fields, excluding its server ID."""
    return (
        entry["action"],
        entry["src"],
        entry["dst"],
        entry["protocol"],
        entry.get("port"),
        entry.get("description", ""),
    )


def build_plan(intent, current_vlans, current_acl):
    """Compare desired state with actual state and return required changes."""

    plan = []

    desired_vlans = {
        int(vlan["id"]): vlan for vlan in intent["vlans"]
    }

    actual_vlans = {
        int(vlan["id"]): vlan for vlan in current_vlans
    }

    # Create missing VLANs or update names that do not match.
    for vlan_id, desired in sorted(desired_vlans.items()):
        current = actual_vlans.get(vlan_id)

        if current is None:
            plan.append(("create_vlan", vlan_id, desired["name"]))

        elif current["name"] != desired["name"]:
            plan.append(("update_vlan", vlan_id, desired["name"]))

    # Delete unwanted VLANs, but always preserve VLAN 1.
    for vlan_id in sorted(actual_vlans):
        if vlan_id != 1 and vlan_id not in desired_vlans:
            plan.append(("delete_vlan", vlan_id))

    # Compare existing ACL entries with the intended rules.

    # Keep only the required number of each ACL rule.
    # This also detects and removes duplicate existing entries.
    from collections import Counter

    desired_counts = Counter(acl_key(rule) for rule in intent["acl"])
    kept_counts = Counter()

    for rule in current_acl:
        key = acl_key(rule)

        if kept_counts[key] < desired_counts[key]:
            kept_counts[key] += 1
        else:
            plan.append(("delete_acl", rule["id"]))

    # Create any ACL rules that are still missing.
    for rule in intent["acl"]:
        key = acl_key(rule)

        if kept_counts[key] < desired_counts[key]:
            plan.append(("create_acl", rule))
            kept_counts[key] += 1

    return plan



def safe_request(client, method, path, data=None, key=None):
    """Send a retry-safe API write request."""

    url = f"{API}{path}"
    failures = 0

    while True:
        if client.token is None:
            client.login()

        headers = {
            "Authorization": f"Bearer {client.token}"
        }

        if key is not None:
            headers["Idempotency-Key"] = key

        try:
            response = requests.request(
                method,
                url,
                json=data,
                headers=headers,
                timeout=5
            )

        except (requests.ConnectionError, requests.Timeout):
            failures += 1

            if failures >= 6:
                raise RuntimeError(
                    f"Too many connection failures: {method} {path}"
                )

            delay = min(2 ** (failures - 1), 8)
            delay += random.uniform(0, 0.5)

            print(f"  Connection failed. Retrying in {delay:.2f}s")
            time.sleep(delay)
            continue

        if response.status_code == 401:
            print("  Token expired. Logging in again...")
            client.login()
            continue

        if response.status_code == 429:
            delay = float(response.headers.get("Retry-After", "1"))
            print(f"  Rate limited. Waiting {delay}s")
            time.sleep(delay)
            continue

        if response.status_code == 503:
            failures += 1

            if failures >= 6:
                raise RuntimeError(
                    f"Too many server failures: {method} {path}"
                )

            delay = min(2 ** (failures - 1), 8)
            delay += random.uniform(0, 0.5)

            print(f"  Server unavailable. Retrying in {delay:.2f}s")
            time.sleep(delay)
            continue


        # A repeated DELETE may return 404 because the first
        # attempt already removed the resource successfully.
        if method.upper() == "DELETE" and response.status_code == 404:
            print("  Resource already absent. DELETE is complete.")
            return response

        response.raise_for_status()
        return response


def apply_plan(client, plan):
    """Apply the planned changes using retry-safe API requests."""

    print("\nApplying synchronization plan...")

    for operation in plan:
        action = operation[0]

        if action in ("create_vlan", "update_vlan"):
            _, vlan_id, name = operation

            print(f"  PUT VLAN {vlan_id}: {name}")

            safe_request(
                client,
                "PUT",
                f"/api/v1/vlans/{vlan_id}",
                data={"name": name}
            )

        elif action == "delete_vlan":
            _, vlan_id = operation

            print(f"  DELETE VLAN {vlan_id}")

            safe_request(
                client,
                "DELETE",
                f"/api/v1/vlans/{vlan_id}"
            )

        elif action == "delete_acl":
            _, entry_id = operation

            print(f"  DELETE ACL {entry_id}")

            safe_request(
                client,
                "DELETE",
                f"/api/v1/acl/entries/{entry_id}"
            )

        elif action == "create_acl":
            _, rule = operation

            # Generate the key once for this logical operation.
            # safe_request() reuses it on every retry.
            key = str(uuid.uuid4())

            print(f"  POST ACL: {rule['description']}")

            safe_request(
                client,
                "POST",
                "/api/v1/acl/entries",
                data=rule,
                key=key
            )

        else:
            raise ValueError(f"Unknown operation: {action}")

    print("All planned operations processed.")


def verify_state(client, intent):
    """Check whether the API matches the desired configuration."""

    print("\nVerifying final API state...")

    current_vlans, current_acl = read_current_state(client)

    remaining = build_plan(intent, current_vlans, current_acl)

    if remaining:
        print("FAILED: API does not match intent.")
        print("Remaining differences:")

        for operation in remaining:
            print(" ", operation)

        return False

    print("SUCCESS: API matches intent. No changes remaining.")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Synchronize VLANs and ACL entries with intent.yaml"
    )
    parser.add_argument(
        "intent_file",
        help="Path to intent YAML file"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show planned changes without applying them"
    )

    args = parser.parse_args()

    # Step 1: Read the desired network configuration.
    with open(args.intent_file, "r", encoding="utf-8") as f:
        intent = yaml.safe_load(f)

    print("WIC2005 Week 7 - API Synchronization")
    print("Student ID suffix:", intent["student_id_last4"])
    print("VLANs in intent:", len(intent["vlans"]))
    print("ACL entries in intent:", len(intent["acl"]))
    print("Dry-run mode:", args.dry_run)

    # Step 2: Connect to the API and read its current state.
    client = Client()
    current_vlans, current_acl = read_current_state(client)

    # Step 3: Display the current VLAN configuration.
    print("\nCurrent VLANs:")
    for vlan in current_vlans:
        print(f"  VLAN {vlan['id']}: {vlan['name']}")

    # Step 4: Display existing ACL entries.
    print("\nCurrent ACL entries:")
    if not current_acl:
        print("  No existing ACL entries.")
    else:
        for entry in current_acl:
            print(
                f"  ACL {entry['id']}: "
                f"{entry['action']} - {entry['description']}"
            )

    # Step 5: Calculate the required changes.
    plan = build_plan(intent, current_vlans, current_acl)

    print("\nSynchronization plan:")

    if not plan:
        print("  No changes needed. API already matches intent.")
    else:
        for index, operation in enumerate(plan, start=1):
            print(f"  {index}. {operation}")

    print(f"\nTotal planned changes: {len(plan)}")

    # Step 6: Dry-run must never modify the API.
    if args.dry_run:
        print("DRY RUN: No changes applied.")
        return

    # Apply only when this is not a dry run.
    apply_plan(client, plan)

    # Read the API state again and verify convergence.
    if not verify_state(client, intent):
        sys.exit(1)
    
if __name__ == "__main__":
    main()



if __name__ == "__main__":
    main()
